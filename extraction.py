import streamlit as st
import google.generativeai as genai
import os
import io
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re
import logging
from typing import Optional, Tuple, Dict, Any
from PIL import Image
from pdf2image import convert_from_bytes
import requests
import base64

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure Vertex AI or Gemini API
def configure_vertex_ai():
    """Configure Gemini API for Vertex AI"""
    try:
        # Set environment variable to use Vertex AI
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        
        # Set project and location environment variables
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "tj-gemini-project")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        # Clean the location value to remove any extra text
        location = location.strip().split()[0]  # Take only the first word (e.g., "us-central1" from "us-central1 (lowa)")
        
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        
        # For Vertex AI, we need to use service account credentials or OAuth2
        # Since you have an API key, let's try a different approach
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        
        # Configure with your Vertex AI API key
        genai.configure(api_key=api_key)
        print("✅ Vertex AI configuration successful")
    except Exception as e:
        print(f"❌ Error configuring Vertex AI: {e}")
        raise

# Initialize Vertex AI configuration
configure_vertex_ai()

# Direct Vertex AI API function
def get_vertex_ai_response(input_text, image=None):
    """Get response from Vertex AI using direct HTTP requests"""
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "tj-gemini-project")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        # Clean the location value
        location = location.strip().split()[0]
        
        # Construct the Vertex AI endpoint URL
        url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/gemini-2.5-flash:streamGenerateContent?key={api_key}"
        
        # Prepare the request payload
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": input_text
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0
            }
        }
        
        # If image is provided, add it to the parts
        if image:
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            payload["contents"][0]["parts"].append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": image_base64
                }
            })
        
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Handle streaming response (list of chunks)
            if isinstance(result, list):
                full_text = ""
                for chunk in result:
                    if "candidates" in chunk and len(chunk["candidates"]) > 0:
                        candidate = chunk["candidates"][0]
                        if "content" in candidate and "parts" in candidate["content"]:
                            for part in candidate["content"]["parts"]:
                                if "text" in part:
                                    full_text += part["text"]
                
                if full_text.strip():
                    # Clean the combined text
                    full_text = full_text.strip()
                    # Remove code block markers if present
                    if full_text.startswith('```'):
                        full_text = full_text[7:].rstrip('```').strip()
                    elif full_text.startswith('```'):
                        full_text = full_text[3:].rstrip('```').strip()
                    # Remove invalid control characters
                    full_text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', full_text)
                    # Remove trailing commas
                    full_text = re.sub(r',\s*([\]\}])', r'\1', full_text)
                    # Fix newlines in keys
                    full_text = re.sub(r'\n\s*"([^"]+)"', r'"\1"', full_text)
                    return full_text
                else:
                    logger.error("No text found in streaming response")
                    return None
            
            # Handle single response
            elif isinstance(result, dict) and "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    content = candidate["content"]["parts"][0]["text"]
                    # Clean the content
                    content = content.strip()
                    if content.startswith('```'):
                        content = content[7:].rstrip('```').strip()
                    elif content.startswith('```'):
                        content = content[3:].rstrip('```').strip()
                    content = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', content)
                    content = re.sub(r',\s*([\]\}])', r'\1', content)
                    content = re.sub(r'\n\s*"([^"]+)"', r'"\1"', content)
                    return content
                else:
                    logger.error("No content found in single response")
                    return None
            else:
                logger.error("No valid response format found")
                return None
        else:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error with Vertex AI request: {e}")
        return None
    
# --- Helper Functions ---
def get_today_date():
    logger.info("Retrieving today's date")
    date = datetime.utcnow().strftime("%Y-%m-%d")
    logger.info(f"Today's date retrieved: {date}")
    return date

def get_daily_request_count():
    logger.info("Fetching daily request count from cache.db")
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    c.execute("SELECT count FROM request_logs WHERE date = ?", (get_today_date(),))
    row = c.fetchone()
    conn.close()
    count = row[0] if row else 0
    logger.info(f"Daily request count retrieved: {count}")
    return count

def increment_request_count():
    logger.info("Incrementing daily request count")
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    today = get_today_date()
    count = get_daily_request_count()
    if count == 0:
        logger.info(f"Inserting new request log for date: {today}")
        c.execute("INSERT INTO request_logs (date, count) VALUES (?, ?)", (today, 1))
    else:
        logger.info(f"Updating request count for date: {today}, new count: {count + 1}")
        c.execute("UPDATE request_logs SET count = ? WHERE date = ?", (count + 1, today))
    conn.commit()
    conn.close()
    logger.info("Request count incremented successfully")

def get_gemini_response(input_text, image=None):
    try:
        response_text = get_vertex_ai_response(input_text, image)
        if response_text:
            return response_text
        else:
            logger.error("No valid response from Vertex AI")
            return None
    except Exception as e:
        logger.error(f"Error with Vertex AI request: {e}")
        return None

def input_file_text(uploaded_file):
    try:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        print(f"🔍 Processing file with extension: {file_extension}")
        print(f"🔍 File name: {uploaded_file.name}")
        print(f"🔍 File size: {uploaded_file.size} bytes")
        
        prompt = ("Extract all text from this document accurately. Preserve formatting, line breaks, and structure as much as possible. "
                  "Handle mixed languages (e.g., English, Tamil, Sinhala) correctly. Return plain text.")
        
        if file_extension == 'pdf':
            print("🔍 Processing PDF file with pdf2image + Vertex AI")
            from pdf2image import convert_from_bytes
            poppler_path = r"C:\Poppler\poppler-25.07.0\Library\bin"
            
            try:
                images = convert_from_bytes(uploaded_file.getvalue(), poppler_path=poppler_path)
                extracted_text = ""
                for i, image in enumerate(images):
                    print(f"🔍 Processing page {i+1}")
                    # Use Vertex AI for text extraction from images
                    response_text = get_vertex_ai_response(prompt, image)
                    if response_text:
                        extracted_text += response_text + "\n"
                        print(f"🔍 Page {i+1} extracted: {len(response_text)} characters")
                    else:
                        print(f"❌ Failed to extract text from page {i+1}")
                        # Fallback: Try OCR with different prompt
                        fallback_response = get_vertex_ai_response("Extract text from this image:", image)
                        if fallback_response:
                            extracted_text += fallback_response + "\n"
                            print(f"🔍 Page {i+1} fallback extracted: {len(fallback_response)} characters")
                
                if not extracted_text.strip():
                    print("❌ No text extracted from PDF, trying alternative approach")
                    return ""
                    
                print(f"✅ Successfully extracted {len(extracted_text)} characters from PDF")
                return normalize_text(extracted_text)
                
            except Exception as e:
                print(f"❌ PDF processing error: {e}")
                return ""
                
        elif file_extension == 'docx':
            print("🔍 Processing DOCX file")
            try:
                import docx
                doc = docx.Document(io.BytesIO(uploaded_file.getvalue()))
                raw_text = "\n".join([para.text for para in doc.paragraphs])
                print(f"🔍 Raw DOCX text: {len(raw_text)} characters")
                
                # Use Vertex AI for text cleaning and enhancement
                enhanced_prompt = f"{prompt}\n\nDocument text to process:\n{raw_text}"
                response_text = get_vertex_ai_response(enhanced_prompt)
                extracted_text = response_text if response_text else raw_text
                
                return normalize_text(extracted_text)
                
            except Exception as e:
                print(f"❌ DOCX processing error: {e}")
                return ""
        
        elif file_extension == 'doc':
            print("🔍 Processing DOC file")
            try:
                import docx2txt
                raw_text = docx2txt.process(io.BytesIO(uploaded_file.getvalue()))
                print(f"🔍 Raw DOC text: {len(raw_text)} characters")
                
                # Use Vertex AI for text cleaning and enhancement
                enhanced_prompt = f"{prompt}\n\nDocument text to process:\n{raw_text}"
                response_text = get_vertex_ai_response(enhanced_prompt)
                extracted_text = response_text if response_text else raw_text
                
                return normalize_text(extracted_text)
                
            except Exception as e:
                print(f"❌ DOC processing error: {e}")
                return ""

        elif file_extension == 'txt':
            print("🔍 Processing TXT file")
            try:
                raw_text = uploaded_file.getvalue().decode("utf-8")
                print(f"🔍 Raw TXT text: {len(raw_text)} characters")
                
                # Use Vertex AI for text cleaning and enhancement
                enhanced_prompt = f"{prompt}\n\nDocument text to process:\n{raw_text}"
                response_text = get_vertex_ai_response(enhanced_prompt)
                extracted_text = response_text if response_text else raw_text
                
                return normalize_text(extracted_text)
                
            except Exception as e:
                print(f"❌ TXT processing error: {e}")
                return ""
        
        elif file_extension == 'odt':  
            print("🔍 Processing ODT file")
            try:
                from odf import text, teletype
                from odf.opendocument import load
                doc = load(io.BytesIO(uploaded_file.getvalue()))
                raw_text = ""
                for element in doc.getElementsByType(text.P):
                    raw_text += teletype.extractText(element) + "\n"
                print(f"🔍 Raw ODT text: {len(raw_text)} characters")
                
                # Use Vertex AI for text cleaning and enhancement
                enhanced_prompt = f"{prompt}\n\nDocument text to process:\n{raw_text}"
                response_text = get_vertex_ai_response(enhanced_prompt)
                extracted_text = response_text if response_text else raw_text
                
                return normalize_text(extracted_text)
                
            except ImportError:
                print("❌ OpenDocument support requires 'odfpy' package. Please install with: pip install odfpy")
                return ""
            except Exception as e:
                print(f"❌ ODT processing error: {e}")
                return ""

        else:
            print(f"❌ Unsupported file format: {file_extension}")
            return ""
            
    except Exception as e:
        print(f"❌ Error in input_file_text: {e}")
        import traceback
        traceback.print_exc()
        return ""

def normalize_text(txt):
    logger.info("Normalizing text")
    txt = re.sub(r'[^\w\s\.\-]', ' ', txt)  # Keep only words, spaces, dots, and hyphens
    txt = re.sub(r'\s+', ' ', txt)  # Replace multiple spaces with single space
    normalized = txt.strip()  # Remove leading spaces
    logger.info(f"Text normalized. Original length: {len(txt)}, Normalized length: {len(normalized)}")
    return normalized

def extract_text_from_image(image):
    try:
        prompt = "Extract all the text from this image accurately. Preserve formatting, line breaks, and structure as much as possible."
        
        # Use the new Vertex AI function instead of the Google Generative AI library
        response_text = get_vertex_ai_response(prompt, image)
        
        if response_text:
            return response_text
        else:
            print("❌ No text extracted from image")
            return ""
            
    except Exception as e:
        print(f"❌ Error with Gemini image extraction: {str(e)}")
        return ""

def count_jobs_in_jd(jd_text: str) -> int:
    """
    Analyzes the provided Job Description (JD) text to determine how many distinct job positions are being advertised.
    
    This function uses Gemini AI to intelligently count the number of jobs by looking for patterns such as:
    - Multiple job titles (e.g., "Software Engineer" and "Data Analyst" in separate sections).
    - Distinct sections or headings for different roles.
    - Listings of multiple positions within the same document.
    - Job titles connected by 'and' in the title or heading (e.g., "Software Engineer and Assistant Software Engineer").
    
    If the JD describes only one job (even with variations or requirements), it returns 1.
    If no valid JD text is provided or analysis fails, returns 0.
    
    Args:
        jd_text (str): The raw or extracted text from the Job Description.
    
    Returns:
        int: The number of distinct jobs identified (e.g., 1 for single job, 2+ for multiple).
    """
    logger.info("Counting jobs in JD text")
    if not jd_text.strip():
        logger.info("No JD text provided, returning 0 jobs")
        return 0

    # Normalize the JD text for consistency
    normalized_jd = normalize_text(jd_text)
    logger.info(f"JD text normalized. Length: {len(normalized_jd)} characters")

    # Prompt for Gemini to count distinct jobs
    count_prompt = """
    You are an expert in analyzing job descriptions. Your task is to determine how many distinct job positions are being advertised in the provided text.
    
    STRICT RULES:
    1. A 'distinct job position' is a separate role with its own title, responsibilities, and/or requirements. For example:
       - If the text has sections like "Job 1: Software Engineer" and "Job 2: Data Analyst", count as 2.
       - If the job title or heading includes multiple roles connected by 'and' (e.g., "Assistant Software Engineer and Software Engineer"), count each role as a separate job (e.g., 2), unless the context clearly indicates they are the same role (e.g., shared responsibilities or requirements).
       - If the JD lists "or" options for the same role (e.g.,  "Junior or Senior Engineer"), count as 1.
       - If the text is a collection of unrelated jobs (e.g., multiple postings in one document), count each.
    2. Scan for indicators like headings, bullet points starting with job titles, repeated structures (e.g., "Position:", "Title:"), or titles connected by 'and' in the job title or introductory text.
    3. Ignore non-job sections like company info, benefits, or application instructions.
    4. If the text describes only one job, return 1.
    5. If no jobs are identifiable, return 0.
    6. Return ONLY the integer number (e.g., 1, 2, 3) with no additional text or explanation.
    
    Job Description Text: {jd_text}
    """

    # Format the prompt with the normalized JD text
    formatted_prompt = count_prompt.format(jd_text=normalized_jd)
    logger.info("Job count prompt formatted")

    # Get response from Gemini
    response = get_gemini_response(formatted_prompt)
    
    if not response:
        logger.error("No response from Gemini for job count")
        return 0

    try:
        # Clean and parse the response (expecting a single integer)
        response = response.strip()
        job_count = int(response)
        logger.info(f"Identified {job_count} jobs in JD")
        return job_count
    except ValueError:
        logger.error(f"Invalid response from Gemini for job count: {response}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error in count_jobs_in_jd: {str(e)}")
        return 0
    
# NEW: Function to detect language using Gemini    
def detect_language(text):
    if not text.strip():
        return "Unknown"
    try:
        prompt = f"Detect the primary language of this text and return only the language name (e.g., 'English', 'Tamil', 'Sinhala', 'Spanish', 'French'): \n\n{text}"  
        response = get_gemini_response(prompt)
        return response.strip() if response else "Unknown"
    except Exception as e:
        print(f"❌ Error detecting language: {e}")
        return "Unknown"


# NEW: Function to translate text to English using Gemini
def translate_to_english(text):
    if not text.strip():
        return text
    try:
        prompt = f"Translate the following text to English, preserving the meaning, structure, formatting, and job description details as much as possible:\n\n{text}"
        response = get_gemini_response(prompt)
        return response if response else text
    except Exception as e:
        print(f"❌ Error translating to English: {e}")
        return text 
    
# --- Cache Setup ---
def init_cache():
    logger.info("Initializing cache database")
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS results_cache
                 (input_hash TEXT PRIMARY KEY, result TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS request_logs (
                    date TEXT PRIMARY KEY,
                    count INTEGER
                )''')
    c.execute("DELETE FROM results_cache WHERE timestamp < ?",
              ((datetime.utcnow() - timedelta(days=30)).isoformat(),))
    conn.commit()
    conn.close()
    logger.info("Cache database initialized successfully")

init_cache()

def hash_input(resume_text, jd_text, weights):
    logger.info("Generating input hash for resume and JD")
    combined = (normalize_text(resume_text) + "||" + normalize_text(jd_text) + "||" + json.dumps(weights)).encode('utf-8')
    input_hash = hashlib.sha256(combined).hexdigest()
    logger.info(f"Input hash generated: {input_hash}")
    return input_hash

def check_cache(input_hash):
    logger.info(f"Checking cache for input hash: {input_hash}")
    try:
        conn = sqlite3.connect('cache.db')
        c = conn.cursor()
        c.execute("SELECT result FROM results_cache WHERE input_hash = ?", (input_hash,))
        result = c.fetchone()
        conn.close()
        if result:
            logger.info("Cache hit: Result found")
            return json.loads(result[0])
        logger.info("Cache miss: No result found")
        return None
    except Exception as e:
        logger.error(f"Error accessing cache: {str(e)}")
        st.error(f"Error accessing cache: {e}")
        return None

def store_cache(input_hash, result):
    logger.info(f"Storing result in cache with hash: {input_hash}")
    try:
        conn = sqlite3.connect('cache.db')
        c = conn.cursor()
        timestamp = datetime.utcnow().isoformat()
        c.execute("INSERT OR REPLACE INTO results_cache (input_hash, result, timestamp) VALUES (?, ?, ?)",
                  (input_hash, json.dumps(result), timestamp))
        conn.commit()
        conn.close()
        logger.info("Result stored in cache successfully")
    except Exception as e:
        logger.error(f"Error storing cache: {str(e)}")
        st.error(f"Error storing cache: {e}")

# Exact Skills Matcher
def get_skills_match_via_gemini(resume_technical, resume_soft, jd_technical, jd_soft):
    """
    Uses Gemini to semantically match skills from resume to JD.
    Returns: score (0.0-1.0), matched_skills (list of dicts with JD skill and matched CV skill), missing_skills (list)
    """
    logger.info("Starting skills matching via Gemini")
    # If JD has no skill requirements, it's a perfect match by default.
    if not (jd_technical or jd_soft):
        logger.info("No JD skill requirements found, returning perfect match")
        return 1.0, [], []

    # Combine the skills into single lists for easier processing
    jd_skills_combined = jd_technical + jd_soft
    resume_skills_combined = resume_technical + resume_soft
    logger.info(f"JD skills: {jd_skills_combined}")
    logger.info(f"Resume skills: {resume_skills_combined}")

    # Create a prompt that instructs Gemini to act as a skill matcher and return mappings
    skills_prompt = """
    ACT AS a precise skills matching engine. Compare the skills required by the Job Description (JD) with the skills present on the Resume.

    INSTRUCTIONS:
    1. ANALYZE the lists of skills below.
    2. For each skill in the "JD SKILLS" list, determine if it is semantically matched by ANY skill in the "RESUME SKILLS" list.
    3. A "match" means the resume skill demonstrates the same or highly related competency. Be semantically intelligent. For example:
       - "QuickBooks Online" matches with "QuickBooks", "QBO", "Bookkeeping".
       - "MS Excel" matches with "Excel", "Advanced Excel", "Spreadsheets".
       - "Attention to Detail" matches with "Detail-Oriented", "Meticulous".
       - "Bank Reconciliation" matches with "Reconciling Accounts", "Financial Reconciliation".
       - "Communication" matches with "Verbal Communication", "Written Skills".
    4. Return a JSON array of objects, where each object contains:
       - "jd_skill": The JD skill that was matched.
       - "cv_skill": The specific resume skill that matched it (choose the most relevant match).
       - If no match is found for a JD skill, do NOT include it in the output.

    JD SKILLS: {jd_skills}
    RESUME SKILLS: {resume_skills}

    OUTPUT MUST BE VALID JSON. Example:
    [
        {{"jd_skill": "Python", "cv_skill": "Python"}},
        {{"jd_skill": "Communication", "cv_skill": "Verbal Communication"}}
    ]
    """

    # Format the prompt with the actual skills lists
    formatted_prompt = skills_prompt.format(
        jd_skills=jd_skills_combined,
        resume_skills=resume_skills_combined
    )
    logger.info("Skills matching prompt formatted")

    # Get the response from Gemini
    response = get_gemini_response(formatted_prompt)
   
    if not response:
        logger.error("Failed to get skills matching response from Gemini")
        st.error("Failed to get skills matching from Gemini.")
        # If API fails, assume no matches
        return 0.0, [], jd_skills_combined

    matched_skills_from_gemini = []
    try:
        # Parse the JSON response from Gemini (should be a list of dicts)
        matched_skills_from_gemini = json.loads(response)
        if not isinstance(matched_skills_from_gemini, list):
            logger.warning("Gemini response is not a list, setting to empty list")
            matched_skills_from_gemini = []
        logger.info(f"Matched skills parsed: {len(matched_skills_from_gemini)} matches")
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error in resume extraction: {str(e)}, line: {e.lineno}, column: {e.colno}, message: {e.msg}")
        st.error(f"JSON parsing error: {e.msg} at line {e.lineno}, column {e.colno}")
        st.code(f"Response that failed to parse:\n{response}", language="text")
        # If parsing fails, assume no matches
        matched_skills_from_gemini = []

    # --- MANUAL SCORE CALCULATION ---
    total_jd_skills = len(jd_skills_combined)
    num_matched = len(matched_skills_from_gemini)
   
    # Calculate the score yourself
    score = num_matched / total_jd_skills if total_jd_skills > 0 else 1.0
    logger.info(f"Skills matching score calculated: {score:.3f} ({num_matched}/{total_jd_skills})")

    # Find the missing skills by comparing the full JD list to the matched list
    matched_jd_skills = [item["jd_skill"] for item in matched_skills_from_gemini]
    missing_skills = [skill for skill in jd_skills_combined if skill not in matched_jd_skills]
    logger.info(f"Missing skills: {missing_skills}")

    # Debugging info
    with st.expander("🔍 Debug: Skills Matching Details", expanded=False):
        st.write("**All JD Skills:**", jd_skills_combined)
        st.write("**All Resume Skills:**", resume_skills_combined)
        st.write("**Gemini's Matched Skills (JD -> CV):**", matched_skills_from_gemini)
        st.write("**Calculation:**", f"{num_matched} / {total_jd_skills} = {score:.3f}")

    logger.info("Skills matching completed")
    return score, matched_skills_from_gemini, missing_skills

def extract_jd_requirements(jd_text):
    """
    Standalone function to extract technical skills, soft skills, education, and experience from JD text.
    Returns a dictionary with the extracted components in JSON format.
    """
    logger.info("Extracting requirements from JD text")
    if not jd_text:
        logger.info("No JD text provided, returning empty requirements")
        return {
            "required_technical": [],
            "required_soft": [],
            "education": [],
            "experience": []
        }

    # Normalize and preprocess the JD text
    normalized_jd = normalize_text(jd_text)
    logger.info(f"JD text normalized. Length: {len(normalized_jd)} characters")
    # Replace multiple newlines or separators with clear section breaks
    normalized_jd = re.sub(r'\n\s*---\s*\n|\n{2,}', '\n\n[SECTION_BREAK]\n\n', normalized_jd)
    # Ensure each section is clearly labeled
    sections = normalized_jd.split('[SECTION_BREAK]')
    processed_jd = ""
    for i, section in enumerate(sections):
        section = section.strip()
        if section:
            processed_jd += f"\n\n[Job Description Section {i+1}]\n{section}\n"
    logger.info(f"JD text processed into {len(sections)} sections")

    # JD Extraction Prompt
    input_prompt_jd_extract = """
    You are an expert ATS scanner. Extract these requirements from the job description in JSON format:
    - required_technical: List of required technical skills (e.g., single words or short phrases like 'Python', 'React')
    - required_soft: List of required soft skills (e.g., single words or short phrases like 'Teamwork', 'Problem Solving')
    - education: List of required degrees or certifications from the Qualifications, Education, Profile, or similar sections, where each requirement is extracted sentence by sentence, treating any sentence containing one or more 'or', '/', 'equivalent', or parenthetical clarifications as a SINGLE requirement
    - experience: List with years/role requirements
    Return valid JSON. Break down complex skill phrases into individual, concise skills (e.g., 'Passion for coding, learning, and problem-solving' -> ['Coding', 'Learning', 'Problem Solving']). Use standardized, concise skill names (e.g., 'React' instead of 'React.js', 'Problem Solving' instead of 'problem-solving ability'). Avoid verbose phrases and ensure skills are single words or short phrases.

    STRICT INSTRUCTIONS FOR SKILLS EXTRACTION:
    1. Scan the ENTIRE job description to identify all required or preferred skills, regardless of section (e.g., Profile, Qualifications, Requirements).
    2. Categorize into technical (tools, technologies, hard proficiencies) and soft (personal qualities, abilities, attitudes, interpersonal traits).
    3. Look for phrases indicating skills, such as "ability to...", "mindset", "skills in...", or listed attributes.
    4. Break down compound phrases into individual skills. For example:
    - 'A positive mindset & ability to handle pressure' -> ['Positive Mindset', 'Ability to Handle Pressure']
    - 'Good communication and teamwork skills' -> ['Communication', 'Teamwork']
    5. Avoid duplicates and use concise, standardized names (e.g., 'ability to handle pressure' -> 'Stress Management' if appropriate, but prefer close to original if not standard).
    6. If no skills are found, return empty lists.

    STRICT INSTRUCTIONS FOR EDUCATION EXTRACTION:
    1. Process the job description SENTENCE BY SENTENCE to identify education requirements from sections labeled 'Qualifications', 'Education', 'Profile', or similar, where a sentence is defined as text ending with a period (.), semicolon (;), or a new line if listed in bullet points.
    2. For each sentence, check for the presence of 'or', '/', 'equivalent', 'or similar qualification', 'or related qualification', 'or a related field', commas separating degrees/certifications, or parenthetical clarifications (e.g., '(AAT/CASL or SL taxation qualification)').
    3. If a sentence contains ANY number of 'or', '/', 'equivalent', or parenthetical content, treat the ENTIRE sentence, including any parentheses, as ONE education requirement and include it as a SINGLE string in the education list, preserving the exact original phrasing, including all connectors and parentheses, to maintain context.
    - **Example**: "y or z in x, or a related field required" -> ["y or z in x, or a related field required"]
    - **Example**: "m or n or o or p" -> ["m or n or o or p"]
    - **Example**: "CA, CMA, ACCA, or equivalent qualification" -> ["CA, CMA, ACCA, or equivalent qualification"]
    4. Do NOT split degrees, certifications, or parenthetical content within a sentence into separate list items, even if they are listed with multiple 'or' connectors, commas, slashes, or parentheses (e.g., 'Partly qualified in recognized accounting or taxation body (AAT/CASL or SL taxation qualification)' must be ONE item).
    - "y or z in m, or a related field required" must NOT be split into ["y in m", "z in m", "Related field"].
    - "h, m, or a related field" must be ONE item: ["h, m, or a related field"].
    5. For sentences with 'and' connecting distinct requirements (e.g., 'Bachelor's in CS and Master's in Data Science'), treat them as SEPARATE requirements in the education list.
    6. If a sentence does not contain 'or', '/', 'equivalent', or parenthetical content and lists a single degree or certification, include it as a single requirement.
    7. Ensure each education requirement is a concise string that retains the full context of the sentence, removing only redundant whitespace or formatting (e.g., bullet points) but preserving all words, punctuation, and parentheses within the sentence.
    8. If a sentence includes 'preferred' (e.g., 'IT technician certification preferred'), include it as a requirement but note it as optional in the string (e.g., 'IT technician certification (preferred)').
    9. If no education requirements are found, return an empty list for education.
    10. Validate that the output JSON strictly follows the example format, with no additional or missing fields.

    # IMPORTANT EXPERIENCE EXTRACTION RULES:
    # 1. If the JD mentions specific years of experience but NO specific role (e.g., "minimum 2 years experience"),
    #    use the job title from the JD as the role.
    # 2. If the JD mentions "related field" or "relevant experience" without specifying exact roles,
    #    use the job title from the JD as the required role.
    # 3. If multiple roles are mentioned, extract the most relevant one for the main position.
    # 4. Always return at least one experience requirement if years are mentioned.
   
    STRICT INSTRUCTIONS FOR EXPERIENCE EXTRACTION:
    1. Identify the job role title(s) from the JD, typically found in the 'Job Title', 'Position', or similar section at the top or within the JD text (e.g., 'Software Engineer'). Display titles as they appear in the JD.
    2. For each experience requirement, extract the year range or single year as a string (e.g., '1-2' for '1-2 years', '3' for 'Minimum 3 years').
    3. If the JD specifies a specific phrase for the experience requirement that describes the type of experience (e.g., '3 years in software engineer', '3 years project management'), use the exact phrase describing the experience as the 'role' field (e.g., 'Software Engineer'), regardless of whether it is preceded by prepositions like 'as', 'in', or 'in a ... role'.
    4. If the JD specifies experience in 'related fields', 'related roles', 'relevant experience', 'similar position', or similar vague qualifiers WITHOUT a specific phrase describing the type of experience (e.g., '3 years experience in related fields'), use ONLY the JD's main job title(s) as the 'role' field. Display titles as they appear in the JD.
    5. If the JD mentions experience without specifying years (e.g., 'prior experience', 'experience preferred', 'experience as a Mechanical Engineer'), return a single experience requirement with:
    - "years": null
    - "role": Use the JD's main job title(s) or the specific role mentioned (e.g., 'Mechanical Engineer' for 'experience as a Mechanical Engineer').
    6. Preserve the exact year range or value as a string in the 'years' field (e.g., '1-2' for '1-2 years', '3' for '3 years'). Do NOT convert ranges to single numbers or compute averages.
    7. If multiple experiences/roles are mentioned, extract each as a separate entry in the list, using the most relevant role for each based on the specific phrase or main job title(s).
    8. If no experience is specified, return an empty list.
    9. Always return at least one experience requirement if years are mentioned, using the above logic for the role.
    10. When extracting job titles for the 'role' field, preserve the exact wording, capitalization, and plurality (singular/plural) as they appear in the JD. Do NOT convert plural forms to singular or modify capitalization unless explicitly stated.
    
    EXAMPLE INPUT (JD):
    Job Title: y/z
    Qualifications:
    - Minimum 2-4 years of experience in related fields

    EXAMPLE OUTPUT:
    {{
    "required_technical": [],
    "required_soft": [],
    "education": [],
    "experience": []
        {{
        "years": "2-4",
        "role": "y/z"
        }}
    ]
    }}

    EXAMPLE INPUT (JD):
    Qualifications:
    - Bachelor's degree or Diploma in Information Technology or Bachelor's degree in BS Information Systems or Bachelor's degree in Business.
    - IT technician certification preferred.
    - Partly qualified in recognized x or y (z/t or l).
    - Minimum 3 years of experience in an IT role (ideally a support role).
    - In-depth knowledge of and troubleshooting experience with Windows and Office applications.
    - A positive mindset & ability to handle pressure.
    - Good communication skills.

    EXAMPLE OUTPUT:
    {{
    "required_technical": ["Windows", "Office Applications"],
    "required_soft": ["Positive Mindset", "Ability to Handle Pressure", "Communication"],
    "education": [
        "Bachelor's degree or Diploma in Information Technology or Bachelor's degree in BS Information Systems or Bachelor's degree in Business",
        "IT technician certification (preferred)",
        "Partly qualified in recognized x or y (z/t or l)"
    ],
    "experience": [
        {{"years": 3, "role": "IT Role"}}
    ]
    }}

    Job Description: {jd_text}
    """

    # Format the prompt with the processed JD text
    prompt = input_prompt_jd_extract.format(jd_text=processed_jd)
    logger.info("JD extraction prompt formatted")

    # Get response from Gemini
    response = get_gemini_response(prompt)
   
    if not response:
        logger.error("No response from Gemini for JD extraction")
        return {
            "required_technical": [],
            "required_soft": [],
            "education": [],
            "experience": []
        }

    try:
        # Clean the response - handle escaped JSON strings
        logger.info("Cleaning Gemini response for JD extraction")
        response = response.strip()
       
        # If response starts and ends with quotes, it's an escaped JSON string
        if response.startswith('"') and response.endswith('"'):
            logger.info("Removing outer quotes from escaped JSON string")
            response = response[1:-1].replace('\\"', '"')
       
        # If response starts and ends with triple quotes (markdown code block)
        if response.startswith('```'):
            logger.info("Removing JSON code block markers")
            response = response[7:-3].strip()
        elif response.startswith('```') and response.endswith('```'):
            logger.info("Removing generic code block markers")
            response = response[3:-3].strip()
       
        # Remove any remaining escape characters
        response = response.replace('\\n', ' ').replace('\\t', ' ')
        logger.info("Escape characters removed from response")
       
        # Remove invalid control characters
        response = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', response)
        logger.info("Invalid control characters removed")
       
        # Remove trailing commas before closing brackets/braces
        response = re.sub(r',\s*([\]\}])', r'\1', response)
        logger.info("Trailing commas removed")
       
        # Fix empty objects and arrays
        response = re.sub(r'\{\s*\}', r'{}', response)
        response = re.sub(r'\[\s*\]', r'[]', response)
        logger.info("Empty objects and arrays fixed")
       
        # Fix whitespace in keys
        response = re.sub(r'"\s*([a-zA-Z_]+)\s*"', r'"\1"', response)
        logger.info("Whitespace in JSON keys fixed")
       
        # Parse the JSON
        extracted_jd = json.loads(response)
        logger.info("JD requirements parsed successfully")
       
        # Validate required keys
        required_jd_keys = ["required_technical", "required_soft", "education", "experience"]
        for key in required_jd_keys:
            if key not in extracted_jd:
                logger.warning(f"Missing key '{key}' in JD extraction, adding empty list")
                extracted_jd[key] = []

        # Ensure lists are properly formatted
        for key in ["required_technical", "required_soft", "education"]:
            if not isinstance(extracted_jd[key], list):
                logger.warning(f"Key '{key}' is not a list, converting to empty list")
                extracted_jd[key] = []
        if not isinstance(extracted_jd["experience"], list):
            logger.warning("Key 'experience' is not a list, converting to empty list")
            extracted_jd["experience"] = []

        logger.info(f"JD extraction completed: {extracted_jd}")
        return extracted_jd

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error in JD extraction: {str(e)}")
        st.error(f"JSON parsing error: {e}")
        st.code(f"Response that failed to parse:\n{response}", language="text")
       
        # Try to manually extract from the response text
        extracted_jd = {
            "required_technical": [],
            "required_soft": [],
            "education": [],
            "experience": []
        }
       
        # Manual extraction patterns
        if "MS Office" in response:
            logger.info("Manually extracted 'MS Office' for required_technical")
            extracted_jd["required_technical"].append("MS Office")
        if "ERP Systems" in response:
            logger.info("Manually extracted 'ERP Systems' for required_technical")
            extracted_jd["required_technical"].append("ERP Systems")
           
        soft_skills = ["Communication", "Teamwork", "Attention to Detail",
                      "Positive Attitude", "Self-Motivation", "Adaptability"]
        for skill in soft_skills:
            if skill in response:
                logger.info(f"Manually extracted soft skill: {skill}")
                extracted_jd["required_soft"].append(skill)
               
        if "Partly qualified in recognized accounting or taxation body" in response:
            logger.info("Manually extracted education requirement")
            extracted_jd["education"].append("Partly qualified in recognized accounting or taxation body (AAT/CASL or SL taxation qualification)")
           
        if "Tax Finance or accounting" in response and "1" in response:
            logger.info("Manually extracted experience requirement")
            extracted_jd["experience"].append({"years": "1", "role": "Tax Finance or accounting"})
           
        logger.info(f"Fallback JD extraction completed: {extracted_jd}")
        return extracted_jd

    except Exception as e:
        logger.error(f"Unexpected error in extract_jd_requirements: {str(e)}")
        st.error(f"Unexpected error in extract_jd_requirements: {e}")
        return {
            "required_technical": [],
            "required_soft": [],
            "education": [],
            "experience": []
        }

def extract_resume_requirements(resume_text):
    """
    Standalone function to extract technical skills, soft skills, education, and experience from resume text.
    Returns a dictionary with the extracted components in JSON format.
    """
    logger.info("Extracting requirements from resume text")
    if not resume_text:
        logger.info("No resume text provided, returning empty requirements")
        return {
            "technical_skills": [],
            "soft_skills": [],
            "education": [],
            "experience": []
        }

    # Normalize and preprocess the resume text
    normalized_resume = normalize_text(resume_text)
    logger.info(f"Resume text normalized. Length: {len(normalized_resume)} characters")
    
    # Replace multiple newlines or separators with clear section breaks
    normalized_resume = re.sub(r'\n\s*---\s*\n|\n{2,}', '\n\n[SECTION_BREAK]\n\n', normalized_resume)
    
    # Ensure each section is clearly labeled
    sections = normalized_resume.split('[SECTION_BREAK]')
    processed_resume = ""
    for i, section in enumerate(sections):
        section = section.strip()
        if section:
            processed_resume += f"\n\n[Resume Section {i+1}]\n{section}\n"
    logger.info(f"Resume text processed into {len(sections)} sections")

    # Format the prompt with the processed resume text
    prompt = input_prompt_extract.format(resume_text=processed_resume)
    logger.info("Resume extraction prompt formatted")

    # Get response from Gemini
    response = get_gemini_response(prompt)
   
    if not response:
        logger.error("No response from Gemini for resume extraction")
        return {
            "technical_skills": [],
            "soft_skills": [],
            "education": [],
            "experience": []
        }

    try:
        # Clean the response - handle escaped JSON strings
        logger.info("Cleaning Gemini response for resume extraction")
        response = response.strip()
       
        # If response starts and ends with quotes, it's an escaped JSON string
        if response.startswith('"') and response.endswith('"'):
            logger.info("Removing outer quotes from escaped JSON string")
            response = response[1:-1].replace('\\"', '"')
       
        # If response starts and ends with triple quotes (markdown code block)
        if response.startswith('```json'):
            logger.info("Removing JSON code block markers")
            response = response[7:-3].strip()
        elif response.startswith('```') and response.endswith('```'):
            logger.info("Removing generic code block markers")
            response = response[3:-3].strip()
       
        # Remove any remaining escape characters
        response = response.replace('\\n', ' ').replace('\\t', ' ')
        logger.info("Escape characters removed from response")
       
        # Remove invalid control characters
        response = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', response)
        logger.info("Invalid control characters removed")
       
        # Remove trailing commas before closing brackets/braces
        response = re.sub(r',\s*([\]\}])', r'\1', response)
        logger.info("Trailing commas removed")
       
        # Fix empty objects and arrays
        response = re.sub(r'\{\s*\}', r'{}', response)
        response = re.sub(r'\[\s*\]', r'[]', response)
        logger.info("Empty objects and arrays fixed")
       
        # Fix whitespace in keys
        response = re.sub(r'"\s*([a-zA-Z_]+)\s*":', r'"\1":', response)
        logger.info("Whitespace in JSON keys fixed")
       
        # Parse the JSON
        extracted_resume = json.loads(response)
        logger.info("Resume requirements parsed successfully")
       
        # Validate required keys
        required_resume_keys = ["technical_skills", "soft_skills", "education", "experience"]
        for key in required_resume_keys:
            if key not in extracted_resume:
                logger.warning(f"Missing key '{key}' in resume extraction, adding empty list")
                extracted_resume[key] = []

        # Ensure lists are properly formatted
        for key in ["technical_skills", "soft_skills", "education"]:
            if not isinstance(extracted_resume[key], list):
                logger.warning(f"Key '{key}' is not a list, converting to empty list")
                extracted_resume[key] = []
        if not isinstance(extracted_resume["experience"], list):
            logger.warning("Key 'experience' is not a list, converting to empty list")
            extracted_resume["experience"] = []

        logger.info(f"Resume extraction completed: {extracted_resume}")
        return extracted_resume

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error in resume extraction: {str(e)}")
        st.error(f"JSON parsing error: {e}")
        st.code(f"Response that failed to parse:\n{response}", language="text")
       
        # Try to manually extract from the response text
        extracted_resume = {
            "technical_skills": [],
            "soft_skills": [],
            "education": [],
            "experience": []
        }
       
        # Manual extraction patterns
        if "Python" in response:
            logger.info("Manually extracted 'Python' for technical_skills")
            extracted_resume["technical_skills"].append("Python")
        if "SQL" in response:
            logger.info("Manually extracted 'SQL' for technical_skills")
            extracted_resume["technical_skills"].append("SQL")
           
        soft_skills = ["Communication", "Teamwork", "Leadership", "Problem Solving"]
        for skill in soft_skills:
            if skill in response:
                logger.info(f"Manually extracted soft skill: {skill}")
                extracted_resume["soft_skills"].append(skill)
               
        if "Bachelor" in response or "B.Sc" in response:
            logger.info("Manually extracted education requirement")
            extracted_resume["education"].append("B.Sc.")
           
        if "Software Engineer" in response and "202" in response:
            logger.info("Manually extracted experience requirement")
            extracted_resume["experience"].append({
                "title": "Software Engineer",
                "details": ["Unknown contributions"],
                "technologies": [],
                "date": "Unknown"
            })
           
        logger.info(f"Fallback resume extraction completed: {extracted_resume}")
        return extracted_resume

    except Exception as e:
        logger.error(f"Unexpected error in extract_resume_requirements: {str(e)}")
        st.error(f"Unexpected error in extract_resume_requirements: {e}")
        return {
            "technical_skills": [],
            "soft_skills": [],
            "education": [],
            "experience": []
        }
    
def get_gemini_model_response(input_text):
    """
    Standalone function to get response from Gemini API and return the used model name as a string.
    Displays the model name (gemini-2.5-flash) via Streamlit toast and print.
    Returns a string in the format 'Model used: {model_name}' or 'Model used: None' if the model fails.
    """
    def get_today_date():
        return datetime.utcnow().strftime("%Y-%m-%d")

    model_name = "gemini-2.5-flash"
    try:
        # Use the new Vertex AI function instead of the Google Generative AI library
        response_text = get_vertex_ai_response(input_text)
        
        if response_text:
            return f"{model_name}"
        else:
            return "None"
            
    except Exception as e:
        print(f"❌ Error with model {model_name}: {e}")
        return "None"

def identify_job_roles(jd_text):
    """
    Identify multiple job roles in a single JD text.
    Returns a list of dictionaries with role information.
    """
    logger.info("Identifying job roles in JD text")
   
    prompt = """
    Analyze this job description and identify if it contains multiple distinct job roles.
    Return a JSON array where each object represents a distinct job role with:
    - "role_title": The title of the job role
    - "role_description": A brief description of the role
    - "keywords": List of keywords/skills specific to this role
   
    If only one role is found, return an array with one object.
   
    Job Description: {jd_text}
   
    Example output for multiple roles:
    [
        {{
            "role_title": "Software Engineer",
            "role_description": "Develops and maintains software applications",
            "keywords": ["Python", "Java", "React", "SQL"]
        }},
        {{
            "role_title": "Data Analyst",
            "role_description": "Analyzes data and creates reports",
            "keywords": ["SQL", "Excel", "Tableau", "Statistics"]
        }}
    ]
    """
   
    formatted_prompt = prompt.format(jd_text=jd_text)
    response = get_gemini_response(formatted_prompt)
   
    if not response:
        logger.warning("Failed to identify job roles, using default single role")
        return [{"role_title": "General Role", "role_description": "General position", "keywords": []}]
   
    try:
        # Clean the response
        response = response.strip()
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1].replace('\\"', '"')
        if response.startswith('```json'):
            response = response[7:-3].strip()
        elif response.startswith('```') and response.endswith('```'):
            response = response[3:-3].strip()
       
        roles = json.loads(response)
        if not isinstance(roles, list):
            roles = [roles]
           
        logger.info(f"Identified {len(roles)} job roles in JD")
        return roles
    except Exception as e:
        logger.error(f"Error parsing job roles: {str(e)}")
        return [{"role_title": "General Role", "role_description": "General position", "keywords": []}]

def find_best_matching_role(resume_text, job_roles):
    """
    Find which job role from the JD best matches the resume.
    Returns the index of the best matching role and a match score.
    """
    logger.info("Finding best matching job role for resume")
   
    if len(job_roles) <= 1:
        logger.info("Only one role found, using it as default")
        return 0, 1.0  # Single role, return index 0 with perfect match
   
    # Extract skills from resume
    resume_prompt = """
    Extract all technical skills from this resume. Return as a JSON array of strings.
    Resume: {resume_text}
    """
   
    formatted_prompt = resume_prompt.format(resume_text=resume_text)
    response = get_gemini_response(formatted_prompt)
   
    resume_skills = []
    if response:
        try:
            resume_skills = json.loads(response)
            if not isinstance(resume_skills, list):
                resume_skills = []
        except:
            resume_skills = []
   
    # Calculate match scores for each role
    best_match_index = 0
    best_match_score = 0
   
    for i, role in enumerate(job_roles):
        role_keywords = role.get("keywords", [])
        if not role_keywords:
            continue
           
        # Calculate match score (percentage of role keywords found in resume)
        matched_keywords = [kw for kw in role_keywords if any(kw.lower() in skill.lower() for skill in resume_skills)]
        match_score = len(matched_keywords) / len(role_keywords) if role_keywords else 0
       
        if match_score > best_match_score:
            best_match_score = match_score
            best_match_index = i
   
    logger.info(f"Best matching role index: {best_match_index}, score: {best_match_score}")
    return best_match_index, best_match_score

def extract_role_specific_requirements(jd_text, target_role_index, all_roles):
    logger.info(f"Extracting requirements for role index: {target_role_index}")
   
    target_role = all_roles[target_role_index]
    role_keywords = target_role.get("keywords", [])
   
    prompt = """
    You are an expert ATS scanner. Extract job requirements specifically relevant to the role: {role_title}
    Role Description: {role_description}
    Role Keywords: {role_keywords}
   
    From this job description, extract requirements relevant to this specific role, including any shared qualifications (e.g., education, certifications) that apply to all roles unless explicitly irrelevant to this role.
    Return valid JSON with:
    - required_technical: List of technical skills (e.g., 'Python')
    - required_soft: List of soft skills (e.g., 'Communication', 'Teamwork')
    - education: List of education requirements (e.g., 'Bachelor's in CS or IT')
    - experience: List of experience requirements (e.g., [{{"years": "n", "role": "m"}}])
   
    INSTRUCTIONS:
    1. Include ALL relevant requirements, including shared qualifications like education or certifications, unless they are explicitly irrelevant to the role (e.g., a different role's specific degree).
    2. For experience, preserve the EXACT year range (e.g., '5-8' for '5-8 years') and role title as stated in the JD. If the JD mentions 'related fields' or 'relevant experience' without a specific role, use the provided role title ({role_title}).
    3. Normalize skills to be concise and consistent with standard ATS terms (e.g., 'Communication' instead of 'communication skills', 'IT Literacy' instead of 'basic IT literacy').
    4. If no experience requirements are found, return an empty experience list.
    5. Ensure output matches the format of general JD extraction for consistency (e.g., same skill naming conventions).
    6. If the role-specific requirements are unclear, include shared qualifications from the JD to avoid missing critical requirements like education.

    Job Description: {jd_text}

    EXAMPLE OUTPUT:
    {{
        "required_technical": ["python"],
        "required_soft": ["Communication", "Teamwork"],
        "education": ["Bachelor's in CS"],
        "experience": [
            {{"years": "5", "role": "Python Developer"}}
        ]
    }}
    """
   
    formatted_prompt = prompt.format(
        role_title=target_role.get("role_title", ""),
        role_description=target_role.get("role_description", ""),
        role_keywords=role_keywords,
        jd_text=jd_text
    )
   
    response = get_gemini_response(formatted_prompt)
   
    if not response:
        logger.warning("Failed to extract role-specific requirements, falling back to general extraction")
        return extract_jd_requirements(jd_text)
   
    try:
        # Clean the response
        response = response.strip()
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1].replace('\\"', '"')
        if response.startswith('```json'):
            response = response[7:-3].strip()
        elif response.startswith('```') and response.endswith('```'):
            response = response[3:-3].strip()
       
        # Remove invalid control characters
        response = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', response)
        # Remove trailing commas
        response = re.sub(r',\s*([\]\}])', r'\1', response)
       
        role_requirements = json.loads(response)
       
        # Validate structure
        required_keys = ["required_technical", "required_soft", "education", "experience"]
        for key in required_keys:
            if key not in role_requirements or not isinstance(role_requirements[key], list):
                logger.warning(f"Missing or invalid key '{key}' in role-specific extraction")
                role_requirements[key] = []
       
        # Normalize skills and education for consistency
        role_requirements["required_technical"] = [normalize_text(skill) for skill in role_requirements["required_technical"]]
        role_requirements["required_soft"] = [normalize_text(skill) for skill in role_requirements["required_soft"]]
        role_requirements["education"] = [normalize_text(edu) for edu in role_requirements["education"]]
       
        # Check for incomplete extraction (e.g., missing education or experience)
        if not role_requirements["education"] or not role_requirements["experience"]:
            logger.warning(f"Incomplete role-specific extraction for {target_role.get('role_title', 'Unknown')}, falling back to general extraction")
            general_requirements = extract_jd_requirements(jd_text)
            if not role_requirements["education"]:
                role_requirements["education"] = general_requirements.get("education", [])
            if not role_requirements["experience"]:
                role_requirements["experience"] = general_requirements.get("experience", [])
       
        # Debug: Display raw response
        with st.expander(f"Debug: Raw Role-Specific JD Response for {target_role.get('role_title', 'Unknown')}", expanded=False):
            st.code(response, language="json")
       
        logger.info(f"Extracted role-specific requirements for {target_role.get('role_title', '')}")
        return role_requirements
    except Exception as e:
        logger.error(f"Error parsing role-specific requirements: {str(e)}")
        st.error(f"Error parsing role-specific requirements: {str(e)}")
        logger.warning("Falling back to general extraction due to parsing error")
        return extract_jd_requirements(jd_text)
   
# Resume Extraction Prompt (Updated)
input_prompt_extract = """
You are an expert ATS scanner. Extract the following information from the provided resume in STRICT JSON format:
{{
  "technical_skills": ["skill1", "skill2"],
  "soft_skills": ["skill1", "skill2"],
  "education": ["degree1", "degree2"],
  "experience": [
    {{
      "title": "Position",
      "details": ["contribution1", "contribution2"],
      "technologies": ["tech1", "tech2"],
      "date": "2020-2025"
    }}
  ]
}}

INSTRUCTIONS FOR SKILLS EXTRACTION:
1. Scan the ENTIRE resume text to identify skills, regardless of where they appear (e.g., skills section, job descriptions, projects, or summary).
2. Use semantic understanding to categorize skills:
   - Technical skills: Programming languages, tools, frameworks, software, cloud platforms, methodologies, or other technical proficiencies (e.g., 'Python', 'AWS', 'Docker', 'Google Colab', 'Streamlit', 'Azure', 'Figma').
   - Soft skills: Interpersonal or professional skills (e.g., 'Leadership', 'Communication', 'Problem Solving').
3. Break down complex phrases or concatenated lists into individual, concise, standardized skill names. For example:
   - 'expertise in Python programming' -> 'Python'
   - 'strong team collaboration skills' -> 'Teamwork'
   - 'Tools and Software R Studio Google Colab Jupiter Notebook Streamlit Weka pickle Visual Studio Eclipse Android Studio Figma Office365' -> ['R Studio', 'Google Colab', 'Jupyter Notebook', 'Streamlit', 'Weka', 'pickle', 'Visual Studio', 'Eclipse', 'Android Studio', 'Figma', 'Office365']
   - 'Cloud Platforms Azure AWS' -> ['Azure', 'AWS']
   - 'Design and Methodologies Database Design Model Integration UML Design UI UX Design Agile' -> ['Database Design', 'Model Integration', 'UML Design', 'UI/UX Design', 'Agile']
4. Avoid duplicates in skill lists by using sets or checking for uniqueness.
5. Ensure skills are single words or short phrases (e.g., 'React' instead of 'React.js', 'Problem Solving' instead of 'problem-solving ability'). Capitalize properly for readability.
6. If text is run together without separators, use context and common knowledge to split into logical skill names (e.g., recognize 'Jupiter Notebook' as 'Jupyter Notebook', 'UI UX Design' as 'UI/UX Design').

Resume: {resume_text}

EXAMPLE OUTPUT:
{{
  "technical_skills": ["Python", "Spring Boot", "SQL", "Google Colab", "Streamlit", "AWS", "Azure"],
  "soft_skills": ["Leadership", "Teamwork", "Communication"],
  "education": ["B.Sc. in CS"],
  "experience": [
    {{
      "title": "Software Engineer",
      "details": ["Built API"],
      "technologies": ["Python"],
      "date": "2020-2025"
    }}
  ]
}}
"""


# JD Extraction Prompt
input_prompt_jd_extract = """
    You are an expert ATS scanner. Extract these requirements from the job description in JSON format:
    - required_technical: List of required technical skills (e.g., single words or short phrases like 'Python', 'React')
    - required_soft: List of required soft skills (e.g., single words or short phrases like 'Teamwork', 'Problem Solving')
    - education: List of required degrees or certifications from the Qualifications, Education, Profile, or similar sections, where each requirement is extracted sentence by sentence, treating any sentence containing one or more 'or', '/', 'equivalent', or parenthetical clarifications as a SINGLE requirement
    - experience: List with years/role requirements
    Return valid JSON. Break down complex skill phrases into individual, concise skills (e.g., 'Passion for coding, learning, and problem-solving' -> ['Coding', 'Learning', 'Problem Solving']). Use standardized, concise skill names (e.g., 'React' instead of 'React.js', 'Problem Solving' instead of 'problem-solving ability'). Avoid verbose phrases and ensure skills are single words or short phrases.

    STRICT INSTRUCTIONS FOR SKILLS EXTRACTION:
    1. Scan the ENTIRE job description to identify all required or preferred skills, regardless of section (e.g., Profile, Qualifications, Requirements).
    2. Categorize into technical (tools, technologies, hard proficiencies) and soft (personal qualities, abilities, attitudes, interpersonal traits).
    3. Look for phrases indicating skills, such as "ability to...", "mindset", "skills in...", or listed attributes.
    4. Break down compound phrases into individual skills. For example:
    - 'A positive mindset & ability to handle pressure' -> ['Positive Mindset', 'Ability to Handle Pressure']
    - 'Good communication and teamwork skills' -> ['Communication', 'Teamwork']
    5. Avoid duplicates and use concise, standardized names (e.g., 'ability to handle pressure' -> 'Stress Management' if appropriate, but prefer close to original if not standard).
    6. If no skills are found, return empty lists.

    STRICT INSTRUCTIONS FOR EDUCATION EXTRACTION:
    1. Process the job description SENTENCE BY SENTENCE to identify education requirements from sections labeled 'Qualifications', 'Education', 'Profile', or similar, where a sentence is defined as text ending with a period (.), semicolon (;), or a new line if listed in bullet points.
    2. For each sentence, check for the presence of 'or', '/', 'equivalent', 'or similar qualification', 'or related qualification', 'or a related field', commas separating degrees/certifications, or parenthetical clarifications (e.g., '(AAT/CASL or SL taxation qualification)').
    3. If a sentence contains ANY number of 'or', '/', 'equivalent', or parenthetical content, treat the ENTIRE sentence, including any parentheses, as ONE education requirement and include it as a SINGLE string in the education list, preserving the exact original phrasing, including all connectors and parentheses, to maintain context.
    - **Example**: "y or z in x, or a related field required" -> ["y or z in x, or a related field required"]
    - **Example**: "m or n or o or p" -> ["m or n or o or p"]
    - **Example**: "CA, CMA, ACCA, or equivalent qualification" -> ["CA, CMA, ACCA, or equivalent qualification"]
    4. Do NOT split degrees, certifications, or parenthetical content within a sentence into separate list items, even if they are listed with multiple 'or' connectors, commas, slashes, or parentheses (e.g., 'Partly qualified in recognized accounting or taxation body (AAT/CASL or SL taxation qualification)' must be ONE item).
    - "y or z in m, or a related field required" must NOT be split into ["y in m", "z in m", "Related field"].
    - "h, m, or a related field" must be ONE item: ["h, m, or a related field"].
    5. For sentences with 'and' connecting distinct requirements (e.g., 'Bachelor's in CS and Master's in Data Science'), treat them as SEPARATE requirements in the education list.
    6. If a sentence does not contain 'or', '/', 'equivalent', or parenthetical content and lists a single degree or certification, include it as a single requirement.
    7. Ensure each education requirement is a concise string that retains the full context of the sentence, removing only redundant whitespace or formatting (e.g., bullet points) but preserving all words, punctuation, and parentheses within the sentence.
    8. If a sentence includes 'preferred' (e.g., 'IT technician certification preferred'), include it as a requirement but note it as optional in the string (e.g., 'IT technician certification (preferred)').
    9. If no education requirements are found, return an empty list for education.
    10. Validate that the output JSON strictly follows the example format, with no additional or missing fields.

    # IMPORTANT EXPERIENCE EXTRACTION RULES:
    # 1. If the JD mentions specific years of experience but NO specific role (e.g., "minimum 2 years experience"),
    #    use the job title from the JD as the role.
    # 2. If the JD mentions "related field" or "relevant experience" without specifying exact roles,
    #    use the job title from the JD as the required role.
    # 3. If multiple roles are mentioned, extract the most relevant one for the main position.
    # 4. Always return at least one experience requirement if years are mentioned.
   
    1. Identify the job role title(s) from the JD, typically found in the 'Job Title', 'Position', or similar section at the top or within the JD text (e.g., 'Junior Operations Assistant/Operations Assistant (Contact Center)').
    2. For each experience requirement, extract the year range or single year as a string (e.g., '1-2' for '1-2 years', '3' for 'Minimum 3 years').
    3. If the JD specifies a specific phrase for the experience requirement that describes the type of experience (e.g., '3 years in logistics or transportation management', '3 years as a Maintenance Engineer', '3 years project management'), use the exact phrase describing the experience as the 'role' field (e.g., 'logistics or transportation management', 'Maintenance Engineer', 'project management'), regardless of whether it is preceded by prepositions like 'as', 'in', or 'in a ... role'.
    4. If the JD specifies experience in 'related fields', 'related roles', 'relevant experience', or similar vague qualifiers WITHOUT a specific phrase describing the type of experience (e.g., '3 years experience in related fields', '3 years of relevant experience'), use ONLY the JD's main job title as the 'role' field.
    5. Do NOT interpret vague qualifiers (e.g., 'related fields', 'relevant experience') as role titles. For example:
    - '3 years in logistics or transportation management' -> Use 'logistics or transportation management'.
    - '3 years as a Logistics Manager' -> Use 'Logistics Manager'.
    - '3 years in related fields' -> Use JD job title (e.g., 'Transport Officer').
    - '3 years experience' -> Use JD job title (e.g., 'Transport Officer').
    6. Preserve the exact year range or value as a string in the 'years' field (e.g., '1-2' for '1-2 years', '3' for '3 years'). Do NOT convert ranges to single numbers or compute averages.
    7. If multiple experiences/roles are mentioned, extract each as a separate entry in the list, using the most relevant role for each based on the specific phrase or main job title.
    8. If no experience is specified, return an empty list.
    9. Always return at least one experience requirement if years are mentioned, using the above logic for the role.

    EXAMPLE INPUT (JD):
    Job Title: y/z
    Qualifications:
    - Minimum 2-4 years of experience in related fields

    EXAMPLE OUTPUT:
    {{
    "required_technical": [],
    "required_soft": [],
    "education": [],
    "experience": [
        {{
        "years": "2-4",
        "role": "y/z"
        }}
    ]
    }}

    EXAMPLE INPUT (JD):
    Qualifications:
    - Bachelor's degree or Diploma in Information Technology or Bachelor's degree in BS Information Systems or Bachelor's degree in Business.
    - IT technician certification preferred.
    - Partly qualified in recognized x or y (z/t or l).
    - Minimum 3 years of experience in an IT role (ideally a support role).
    - In-depth knowledge of and troubleshooting experience with Windows and Office applications.
    - A positive mindset & ability to handle pressure.
    - Good communication skills.

    EXAMPLE OUTPUT:
    {{
    "required_technical": ["Windows", "Office Applications"],
    "required_soft": ["Positive Mindset", "Ability to Handle Pressure", "Communication"],
    "education": [
        "Bachelor's degree or Diploma in Information Technology or Bachelor's degree in BS Information Systems or Bachelor's degree in Business",
        "IT technician certification (preferred)",
        "Partly qualified in recognized x or y (z/t or l)"
    ],
    "experience": [
        {{"years": 3, "role": "IT Role"}}
    ]
    }}

    Job Description: {jd_text}
    """

# Experience Analysis Prompt
input_prompt_experience = """
Analyze the resume's experience section against the JD requirements. Today's date is {current_date}. Return JSON with:
- score: 0.0-1.0 (MUST follow strict scoring rules)
- resume_total_experience: Total RELEVANT professional years (sum of all valid roles that match JD requirements)
- jd_min_experience: Minimum years required
- explanation: Calculation steps with
                if 'matched_roles' in exp_result:
                    total_exp = sum(role.get('duration', 0) for role in exp_result['matched_roles'])
                    resume_exp_years = round(total_exp, 2)
                else:
                    resume_exp_years = exp_result.get("resume_total_experience", 0)
- matched_roles: List of counted roles (only those relevant to JD)
- missing_roles: [] if score=1.0

STRICT SCORING RULES (MUST FOLLOW EXACTLY):
1. IF resume_total_experience ≥ jd_min_experience THEN score=1.0
2. IF resume_total_experience < jd_min_experience THEN score=(resume_total_experience/jd_min_experience)
3. IF no dated professional experience THEN score=0.0

ROLE RELEVANCE RULES:
- Only count experience that matches or is similar to the roles mentioned in JD requirements (RELEVANT internship must be calculated)
- For technical roles, check if technologies used match JD requirements
- For management roles, check if responsibilities align with JD
- Ignore completely unrelated experience including the irrelevant internships

DO NOT CAP OR MODIFY THE SCORE BEYOND THESE RULES.
NEVER show scores >1.0. When requirements are met, score MUST BE EXACTLY 1.0.

COUNTING RULES:
- "Present" = until {current_date}
- Sum ALL valid professional experience periods
- Convert partial years to decimals (e.g., 6 months=0.5)
- Valid date formats:
  * MM/YYYY-MM/YYYY or MM-YYYY-MM-YYYY
  * YYYY-YYYY (full calendar years)
  * "X years" (exact number)
  * "Present" counts until today

Resume Experience: {resume_experience}
JD Requirements: {jd_experience}

RETURN STRICT JSON:
{{
  "score": [MUST BE 0.0-1.0],
  "resume_total_experience": [sum of all valid experience],
  "jd_min_experience": [required years],
  "explanation": "1. Summed all valid roles...",
  "matched_roles": [
    {{
      "title": "Role",
      "duration": X.Y,
      "dates": "YYYY-YYYY"
    }}
  ],
  "missing_roles": []
}}
"""

# Education Analysis Prompt (Updated)
input_prompt_education = """
Analyze education match based on the JD's requirements. Return JSON with:
- score: 0.0-1.0 (calculated strictly based on the rules below)
- individual_scores: List of objects with fields 'degree', 'score', 'explanation' for each required degree in JD
- explanation: Detailed justification, including level matches, field relevance, institution recognition, and how the overall score was calculated
- is_related_field: Boolean (true if any match is based on related field rather than exact)
- matched_education: List of matching qualifications from resume
- missing_education: List of missing requirements from JD

RULES FOR SCORING (MUST FOLLOW EXACTLY IN THIS ORDER):

STEP 1: INTERPRET JD REQUIREMENT
- Read the JD's education requirement sentence by sentence.
- For each sentence, determine if it is a SINGLE requirement (using "or" / "or a related field" / "or related field" / "/" / "equivalent") or MULTIPLE requirements (using "and").
- If a sentence contains "or", "/", or "equivalent", treat the entire sentence as a SINGLE requirement, even if it lists multiple fields or levels (e.g., 'Bachelor's in CS or SE' or 'Bachelor's degree or MBA in Finance or Accounting' is ONE requirement).
- **SINGLE REQUIREMENT EXAMPLE:** "Bachelor's in CS, SE, or a related field" or "Bachelor's degree or MBA in Finance or Accounting" -> ONE requirement.
- **MULTIPLE REQUIREMENTS EXAMPLE:** "Bachelor's in CS and a Master's in Data Science" -> TWO requirements.

STEP 2: SCORING FOR A *SINGLE* JD REQUIREMENT (USING "OR", "/", OR "EQUIVALENT")
- This is ONE requirement that can be fulfilled in multiple ways.
- Search the resume for the HIGHEST qualification that satisfies ANY of the conditions in the requirement (exact or related field if allowed).
- If a match is found that satisfies any condition (exact OR related field if allowed), the score for this single requirement is 1.0 (100%).
- **Example:** JD requires "Bachelor's degree or MBA in Finance or Accounting". Resume has "B.Sc. in Finance". -> Score = 1.0.
- **Example:** JD requires "CA, CMA, ACCA, or equivalent qualification". Resume has "CA". -> Score = 1.0.
- Return only ONE individual_score entry with the score 1.0.

STEP 3: SCORING FOR *MULTIPLE* JD REQUIREMENTS (USING "AND")
- Only use this step if the JD has multiple distinct requirements.
- For each individual requirement in the JD, calculate a score based on the rules below.
- The overall score is the average of these individual scores.

DETAILED MATCHING RULES (For use in STEP 3 or for defining matches in STEP 2):
1. Define education levels hierarchically:
   - Diploma/Certificate: Level 1
   - Bachelor's (BSc, BA, etc., including currently pursuing): Level 2
   - Master's (MSc, MA, MBA, etc., including currently pursuing): Level 3
   - PhD/Doctorate: Level 4
2. For each required degree in JD, calculate an individual match score:
   - Exact match (same level, same field, recognized institution): 1.0
   - Related field (same level or higher, similar domain, e.g., Finance vs. Accounting vs. Business Administration; Computer Science vs. Information Technology vs. Data Science vs. Software Engineering): 0.8
   - If JD explicitly includes 'or a related field', 'or equivalent', or similar (e.g., 'or comparable discipline'), treat related fields as exact matches (score 1.0 for same level or higher)
   - Higher level in same/related field covers lower levels (e.g., Master's covers Bachelor's requirement in same field): Treat as 1.0 for the lower requirement
   - Lower level only:
     - Bachelor's for Master's requirement: 0.5 if same field, 0.4 if related field
     - Diploma for Bachelor's requirement: 0.5 if same field, 0.3 if related field
     - Diploma for Master's requirement: 0.3 if same field, 0.2 if related field
     - No match: 0.0
   - If JD specifies 'currently pursuing' or similar, treat a degree in progress at the specified level as equivalent to a completed degree (score per above rules)
   - Professional certifications (e极A, CMA, ACCA) are treated as Level 2 (equivalent to Bachelor's) unless specified otherwise in the JD
3. Fields are related if in the same domain (e.g., Finance, Accounting, Business Administration are related; Computer Science, Information Technology, Data Science, Software Engineering are related; Finance and Biology are not unless specified). Other fields (e.g., Economics for Finance) are related only if explicitly listed in the JD or if 'or a related field' is included.
4. CLARIFICATION:
   - Assume ALL institutions are recognized unless EXPLICITLY stated as unaccredited in the resume or JD (e.g., 'unaccredited institution'). Do NOT apply any penalty for unknown institutions.
   - If JD includes 'or a related field', 'or equivalent', or similar, treat related fields (e.g., Accounting or Business Administration for Finance; Information Technology or Data Science for Computer Science) as exact matches (score 1.0 for same level, 0.5 for lower level like Bachelor's for Master's).
   - For sentences like 'Bachelor's degree or MBA in Finance or Accounting' or 'CA, CMA, ACCA, or equivalent qualification', treat the entire sentence as ONE requirement. If the resume has any one of the listed qualifications (e.g., 'B.Sc. in Finance' or 'CA'), it satisfies the requirement fully (score 1.0). The explanation must state: 'The JD requires [full requirement text], treated as a single requirement. The resume's [matched qualification] satisfies this requirement fully, scoring 1.0.'

Resume Education: {resume_education}
JD Requirements: {jd_education}

RETURN STRICT JSON:
{{
  "score": 0.0,
  "individual_scores": [
    {{
      "degree": "JD degree requirement",
      "score": 0.0,
      "explanation": "Explanation of match"
    }}
  ],
  "explanation": "Detailed justification",
  "is_related_field": false,
  "matched_education": [],
  "missing_education": []
}}
"""

# Streamlit UI
st.set_page_config(page_title="ATS Resume Analyzer", layout="wide")
st.header("✨Advanced Resume Analysing and Scoring System 📊🚀")
st.sidebar.markdown("### Gemini API Usage")
used = get_daily_request_count()
max_limit = 50
st.sidebar.progress(min(used / max_limit, 1.0), text=f"{used} / {max_limit} used today")

# JD Input Section
st.subheader("Provide Job Description")
col1, col2 = st.columns(2)
with col1:
    jd_text = st.text_area("Paste the Job Description (Optional):", height=300)
with col2:
    # Explicitly allow multiple files and specify allowed extensions
    allowed_extensions = [".png", ".jpg", ".jpeg"]
    jd_images = st.file_uploader(
        "Upload Job Description Images (Optional, PNG, JPG, JPEG; Multiple files allowed):",
        type=allowed_extensions,
        accept_multiple_files=True,
        help="Upload one or more images in PNG, JPG, or JPEG format. All images will be processed and combined into a single job description."
    )
    if jd_images:
        st.info(f"Supported image formats: {', '.join(allowed_extensions)}. Ensure all uploaded files have valid extensions.")
        # Debug: Display raw filenames
        st.markdown("**Debug: Uploaded Filenames**")
        for idx, jd_image in enumerate(jd_images, 1):
            st.write(f"File {idx}: {repr(jd_image.name)}")

# Process JD input
jd = ""
if jd_images:
    extracted_texts = []
    valid_extensions = {ext.lower() for ext in allowed_extensions}
    for idx, jd_image in enumerate(jd_images, 1):
        # Normalize and validate file extension
        file_name = jd_image.name.strip()  # Remove leading/trailing whitespace
        logger.info(f"Processing file {idx}: Raw filename = {repr(file_name)}")
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext not in valid_extensions:
            logger.warning(f"Skipping file '{file_name}' due to invalid extension: {file_ext}")
            st.warning(f"Skipping file '{file_name}' due to invalid extension: {file_ext}. Allowed: {', '.join(allowed_extensions)}")
            continue
       
        try:
            # Display the uploaded image
            st.image(jd_image, caption=f"Uploaded JD Image {idx}: {file_name}", use_column_width=True)
            jd_image.seek(0)  # Reset file pointer
            img = Image.open(jd_image)
            extracted_jd = extract_text_from_image(img)
            if extracted_jd:
                extracted_texts.append(extracted_jd)
                logger.info(f"Extracted text from image '{file_name}': {len(extracted_jd)} characters")
            else:
                logger.warning(f"No text extracted from image '{file_name}'")
                st.warning(f"No text extracted from image '{file_name}'.")
        except Exception as e:
            logger.error(f"Error processing image '{file_name}': {str(e)}")
            st.error(f"Error processing image '{file_name}': {str(e)}")

    if extracted_texts:
        # Combine all extracted texts with a separator, mimicking original behavior
        jd = "\n---\n".join([text.strip() for text in extracted_texts if text.strip()])
        logger.info(f"Combined {len(extracted_texts)} image texts into JD: {len(jd)} characters")

# NEW: Detect JD language and translate to English if not English
if jd:
    detected_language = detect_language(jd)  # Use the separate function to detect and return language
    st.info(f"Detected JD language: {detected_language}")
    
    if detected_language.lower() != "english":
        translated_jd = translate_to_english(jd)
        jd = translated_jd  # Replace original jd with translated for further processing
    else:
        translated_jd = jd


# Display combined extracted JD text (now the English/translated version)
if jd:
    st.markdown("### Extracted Job Description Text")
    st.markdown(
        f"""
        <div style="border: 1px solid #ccc; padding: 10px; width: 100%; white-space: pre-wrap; overflow: hidden; text-align: left;">
            {translated_jd}  
        </div>
        """,
        unsafe_allow_html=True
    )

# if jd_text:
#     if jd:  # If image text exists, append text with separator
#         jd += "\n---\n" + jd_text.strip()
#     else:
#         jd = jd_text.strip()

# # Display combined extracted JD text
# if jd:
#     st.markdown("### Extracted Job Description Text")
#     st.markdown(
#         f"""
#         <div style="border: 1px solid #ccc; padding: 10px; width: 100%; white-space: pre-wrap; overflow: hidden; text-align: left;">
#             {jd}
#         </div>
#         """,
#         unsafe_allow_html=True
#     )

# Normalize JD text
if jd:
    jd = normalize_text(jd)

# Resume Input
with col2:
    uploaded_file = st.file_uploader("Upload Candidate Resume:", type=["pdf", "docx", "txt", "odt", "doc"])
    resume_text = ""  # Initialize empty resume text

if uploaded_file:
    # Store the uploaded file in session state to avoid re-processing
    if 'resume_file' not in st.session_state or st.session_state.resume_file != uploaded_file:
        st.session_state.resume_file = uploaded_file
        st.session_state.resume_text = input_file_text(uploaded_file)
    
    resume_text = st.session_state.resume_text
    
    if resume_text:
        st.markdown("### Extracted CV Text")
        st.markdown(
            f"""
            <div style="border: 1px solid #ccc; padding: 10px; width: 100%; white-space: pre-wrap; overflow: hidden; text-align: left;">
                {resume_text}
            </div>
            """,
            unsafe_allow_html=True
        )

# --- Function Response Testing Section ---
st.subheader("🧪 Test Function Responses")
st.markdown("This section tests the responses of `get_gemini_model_response`, `extract_jd_requirements`, and `extract_resume_requirements` using the provided Job Description and Resume text.")
# Test get_gemini_model_response
st.markdown("#### Test `get_gemini_model_response`")
if jd:
    # Use the JD text as a sample input_text for get_gemini_model_response
    test_input_text = input_prompt_jd_extract.replace("{jd_text}", jd)
    st.markdown("**Input Text for Testing (JD Extraction Prompt with Provided JD):**")
    st.code(test_input_text, language="text")
   
    if st.button("Test get_gemini_model_response", key="test_gemini"):
        with st.spinner("Testing get_gemini_model_response..."):
            model_response = get_gemini_model_response(test_input_text)
            if model_response != "Model used: None":
                st.success(f"Response: {model_response}")
            else:
                st.error("No model was used successfully.")
else:
    st.warning("Please provide a Job Description to test get_gemini_model_response.")


# Test count_jobs_in_jd
st.markdown("#### Test `count_jobs_in_jd`")
if jd:
    st.markdown("**Input JD Text for Testing:**")
    st.code(jd, language="text")
   
    if st.button("Test count_jobs_in_jd", key="test_count_jobs"):
        with st.spinner("Counting jobs in Job Description..."):
            job_count = count_jobs_in_jd(jd)
            if job_count > 0:
                st.success(f"Number of jobs identified in JD: {job_count}")
            else:
                st.error("No jobs identified or analysis failed.")
else:
    st.warning("Please provide a Job Description to test count_jobs_in_jd.")

# Test detect_language
st.markdown("#### Test `detect_language`")
if jd_images or jd_text:
    # Use the raw JD text before any normalization or translation
    raw_jd = ""
    if jd_images:
        extracted_texts = []
        valid_extensions = {".png", ".jpg", ".jpeg"}
        for idx, jd_image in enumerate(jd_images, 1):
            file_ext = os.path.splitext(jd_image.name)[1].lower()
            if file_ext not in valid_extensions:
                continue
            try:
                jd_image.seek(0)
                img = Image.open(jd_image)
                extracted_text = extract_text_from_image(img)
                if extracted_text:
                    extracted_texts.append(extracted_text)
            except Exception as e:
                logger.error(f"Error processing image '{jd_image.name}': {str(e)}")
        if extracted_texts:
            raw_jd = "\n---\n".join([text.strip() for text in extracted_texts if text.strip()])
    elif jd_text:
        raw_jd = jd_text.strip()

    if raw_jd:
        st.markdown("**Input JD Text for Language Detection (Raw):**")
        st.code(raw_jd, language="text")
        
        if st.button("Test detect_language", key="test_detect_language"):
            with st.spinner("Detecting language..."):
                detected_language = detect_language(raw_jd)
                if detected_language and detected_language != "Unknown":
                    st.success(f"Detected JD language: {detected_language}")
                else:
                    st.error("Failed to detect language or no language detected.")
    else:
        st.warning("No valid Job Description text extracted from images or input.")
else:
    st.warning("Please provide a Job Description (text or images) to test detect_language.")

# Test extract_jd_requirements
st.markdown("#### Test `extract_jd_requirements`")
if jd:
    st.markdown("**Input JD Text for Testing:**")
    st.code(jd, language="text")
   
    if st.button("Test extract_jd_requirements", key="test_jd_extract"):
        with st.spinner("Testing extract_jd_requirements..."):
            jd_requirements = extract_jd_requirements(jd)
            st.success("Response from extract_jd_requirements:")
            st.code(json.dumps(jd_requirements, indent=2), language="json")
else:
    st.warning("Please provide a Job Description to test extract_jd_requirements.")

# Test extract_resume_requirements - FIXED VERSION
st.markdown("#### Test `extract_resume_requirements`")
if uploaded_file and resume_text:  # Check if resume_text exists (not just uploaded_file)
    st.markdown("**Input Resume Text for Testing:**")
    st.code(resume_text, language="text")
   
    if st.button("Test extract_resume_requirements", key="test_resume_extract"):
        with st.spinner("Testing extract_resume_requirements..."):
            resume_requirements = extract_resume_requirements(resume_text)
            st.success("Response from extract_resume_requirements:")
            st.code(json.dumps(resume_requirements, indent=2), language="json")
else:
    st.warning("Please upload a resume to test extract_resume_requirements.")

st.subheader("Evaluation Weights")
skills_weight, experience_weight, education_weight = st.columns(3)
with skills_weight:
    skills_w = st.slider("Skills Weight (%)", 0, 100, 50)
with experience_weight:
    exp_w = st.slider("Experience Weight (%)", 0, 100, 30)
with education_weight:
    edu_w = st.slider("Education Weight (%)", 0, 100, 20)

if skills_w + exp_w + edu_w != 100:
    st.error("⚠️ Weights must sum to 100%")
    st.stop()

section_weights = {
    "SKILLS": skills_w / 100,
    "EXPERIENCE": exp_w / 100,
    "EDUCATION": edu_w / 100
}

st.markdown("""
    <style>
    .stButton>button { background-color: #4CAF50; color: white; border-radius: 4px; }
    .progress-bar { height: 25px; background-color: #4CAF50; border-radius: 5px; text-align: center; color: white; font-weight: bold; }
    .match-item { background-color: #e8f5e9; padding: 0.5rem; border-left: 4px solid #4CAF50; margin-bottom: 5px; }
    </style>
""", unsafe_allow_html=True)


# Process Resume and JD
if uploaded_file and jd:
    resume_text = input_file_text(uploaded_file)
    if not resume_text:
        st.stop()

    # Debug: Display raw resume text
    with st.expander("Debug: Raw Resume Text", expanded=False):
        st.write(resume_text)

    # Identify job roles in JD
    job_roles = identify_job_roles(jd)
   
    # Find the best matching role for the resume
    best_role_index, match_score = find_best_matching_role(resume_text, job_roles)
    selected_role = job_roles[best_role_index]
   
    # Display the selected role for comparison
    st.markdown("### 🎯 Selected Job Role for Comparison")
    st.info(f"**Role Title:** {selected_role.get('role_title', 'Unknown')}")
    st.info(f"**Role Description:** {selected_role.get('role_description', 'No description available')}")
    st.info(f"**Match Score:** {match_score:.2%}")
   
    if len(job_roles) > 1:
        st.markdown("#### All Identified Job Roles")
        for i, role in enumerate(job_roles):
            role_title = role.get('role_title', f'Role {i+1}')
            match_indicator = " ✅" if i == best_role_index else ""
            st.write(f"{i+1}. {role_title}{match_indicator}")

    # Extract role-specific requirements
    extracted_jd = extract_role_specific_requirements(jd, best_role_index, job_roles)
   
    input_hash = hash_input(resume_text, jd, section_weights)

    cached_extract = check_cache(input_hash + "_extract")
    if cached_extract:
        extracted_resume = cached_extract
    else:
        response_extract = get_gemini_response(input_prompt_extract.format(resume_text=resume_text))
        if not response_extract:
            st.error("No response from Gemini API for resume extraction.")
            st.stop()
       
        try:
            # Debug: Display raw Gemini response and cleaned JSON attempt
            with st.expander("Debug: Raw Gemini Resume Response", expanded=False):
                st.write("Raw Response:")
                st.write(response_extract)
           
            # Clean JSON string to handle newlines and common JSON errors
            json_str = re.sub(r'\n\s*', ' ', response_extract)  # Remove newlines
            json_str = re.sub(r'\s+', ' ', json_str).strip()  # Normalize whitespace
            json_str = re.sub(r',(\s*[\]\}])', r'\1', json_str)  # Remove trailing commas
            json_str = re.sub(r'\{\s*\}$', r'{}', json_str)  # Fix empty objects
            json_str = re.sub(r'"\s*technical_skills\s*"', '"technical_skills"', json_str)  # Fix newlines in keys
            json_str = re.sub(r'"\s*soft_skills\s*"', '"soft_skills"', json_str)  # Fix newlines in keys
           
            with st.expander("Debug: Cleaned JSON String", expanded=False):
                st.write("Cleaned JSON:")
                st.write(json_str)
           
            try:
                extracted_resume = json.loads(json_str)
            except json.JSONDecodeError as e:
                # Attempt to fix unclosed brackets or incomplete JSON
                if json_str.count('{') > json_str.count('}'):
                    json_str += '}'
                elif json_str.count('[') > json_str.count(']'):
                    json_str += ']'
                try:
                    extracted_resume = json.loads(json_str)
                except json.JSONDecodeError:
                    # Ultimate fallback: Use default JSON structure
                    st.warning("Failed to parse Gemini resume response as JSON. Using default structure.")
                    extracted_resume = {
                        "technical_skills": [],
                        "soft_skills": [],
                        "education": [],
                        "experience": []
                    }
           
            # Validate required keys
            required_keys = ["technical_skills", "soft_skills", "education", "experience"]
            for key in required_keys:
                if key not in extracted_resume:
                    st.warning(f"Missing key '{key}' in resume extraction. Using empty list as fallback.")
                    extracted_resume[key] = []
           
            store_cache(input_hash + "_extract", extracted_resume)
           
        except Exception as e:
            st.error(f"Error processing resume extraction: {e}")
            st.error(f"Raw response: {response_extract}")
            st.stop()
            
    # Display extracted resume information
    with st.expander("📄 View Extracted Resume Information", expanded=False):
        if isinstance(extracted_resume, dict):
            cols = st.columns(3)
            with cols[0]:
                if extracted_resume.get("technical_skills") or extracted_resume.get("soft_skills"):
                    st.markdown("### Skills")
                    if extracted_resume.get("technical_skills"):
                        st.markdown("*Technical Skills*")
                        for skill in extracted_resume["technical_skills"]:
                            st.markdown(f"- {skill}")
                    if extracted_resume.get("soft_skills"):
                        st.markdown("*Soft Skills*")
                        for skill in extracted_resume["soft_skills"]:
                            st.markdown(f"- {skill}")
            with cols[1]:
                if extracted_resume.get("education"):
                    st.markdown("### Education")
                    for edu in extracted_resume["education"]:
                        st.markdown(f"- {edu}")
            with cols[2]:
                if extracted_resume.get("experience"):
                    st.markdown("### Experience")
                    for exp in extracted_resume["experience"]:
                        st.markdown(f"*{exp.get('title', 'Untitled')}*")
                        if exp.get("date"):
                            st.markdown(f"{exp['date']}")

    # Display extracted JD information
    with st.expander("📋 View Extracted JD Information", expanded=False):
        if isinstance(extracted_jd, dict):
            cols = st.columns(3)
            with cols[0]:
                if extracted_jd.get("required_technical") or extracted_jd.get("required_soft"):
                    st.markdown("### Required Skills")
                    if extracted_jd.get("required_technical"):
                        st.markdown("*Technical Skills*")
                        for skill in extracted_jd["required_technical"]:
                            st.markdown(f"- {skill}")
                    if extracted_jd.get("required_soft"):
                        st.markdown("*Soft Skills*")
                        for skill in extracted_jd["required_soft"]:
                            st.markdown(f"- {skill}")
            with cols[1]:
                if extracted_jd.get("education"):
                    st.markdown("### Required Education")
                    for edu in extracted_jd["education"]:
                        st.markdown(f"- {edu}")
            with cols[2]:
                if extracted_jd.get("experience"):
                    st.markdown("### Required Experience")
                    for exp in extracted_jd["experience"]:
                        role = exp.get("role", "Untitled")
                        years = exp.get("years", "Not specified")
                        st.markdown(f"*{role}*")
                        st.markdown(f"{years} years")

    if st.button("🔍 Run Comprehensive Analysis", type="primary"):
        cached_result = check_cache(input_hash + "_result")
        if cached_result:
            result = cached_result
        else:
            with st.spinner("Analyzing resume..."):
                # Step 1: Identify job roles from JD
                job_roles = identify_job_roles(jd)
                logger.info(f"Identified {len(job_roles)} job roles: {[role['role_title'] for role in job_roles]}")

                # Step 2: Find the best-matching role
                best_role_index, match_score = find_best_matching_role(resume_text, job_roles)
                selected_role = job_roles[best_role_index]
                logger.info(f"Selected role: {selected_role['role_title']} with match score: {match_score}")

                # Step 3: Extract role-specific JD requirements
                extracted_jd = extract_role_specific_requirements(jd, best_role_index, job_roles)
                logger.info(f"Role-specific JD requirements: {extracted_jd}")

                # Step 4: Calculate skills score
                skills_score, matched_skills, missing_skills = get_skills_match_via_gemini(
                    extracted_resume.get("technical_skills", []),
                    extracted_resume.get("soft_skills", []),
                    extracted_jd.get("required_technical", []),
                    extracted_jd.get("required_soft", [])
                )

                current_date = datetime.now().strftime("%Y-%m-%d")

                # Step 5: Extract JD role for experience analysis
                jd_role = None
                if extracted_jd.get("experience"):
                    try:
                        jd_role = extracted_jd["experience"][0].get("role", "").lower()
                    except:
                        jd_role = selected_role.get("role_title", "").lower()

                # Step 6: Experience analysis
                exp_response = get_gemini_response(
                    input_prompt_experience.format(
                        current_date=current_date,
                        resume_experience=json.dumps({
                            "experiences": extracted_resume.get("experience", []),
                            "jd_role": jd_role,
                            "jd_technologies": extracted_jd.get("required_technical", [])
                        }),
                        jd_experience=json.dumps(extracted_jd.get("experience", []))
                    )
                )

                try:
                    exp_result = json.loads(exp_response)
                    exp_score = exp_result.get("score", 0.0)
                    exp_explanation = exp_result.get("explanation", "No analysis provided")

                    if 'matched_roles' in exp_result:
                        total_exp = sum(role.get('duration', 0) for role in exp_result['matched_roles'])
                        resume_exp_years = round(total_exp, 2)
                    else:
                        resume_exp_years = exp_result.get("resume_total_experience", 0)

                    jd_min_exp = exp_result.get("jd_min_experience", 0)

                    if 'matched_roles' in exp_result:
                        calculated_total = sum(role.get('duration', 0) for role in exp_result['matched_roles'])
                        if abs(resume_exp_years - calculated_total) > 0.1:
                            st.warning(f"Note: Experience total adjusted from {resume_exp_years} to {calculated_total} based on role relevance")
                            resume_exp_years = calculated_total
                except Exception as e:
                    st.error(f"Error parsing experience analysis: {str(e)}")
                    exp_score = 0.0
                    exp_explanation = "Failed to analyze experience"
                    resume_exp_years = 0
                    jd_min_exp = 0

                # Step 7: Education analysis
                edu_response = get_gemini_response(input_prompt_education.format(
                    resume_education=json.dumps(extracted_resume.get("education", [])),
                    jd_education=json.dumps(extracted_jd.get("education", []))
                ))
                try:
                    edu_result = json.loads(edu_response)
                    edu_score = edu_result.get("score", 0.0)
                    edu_explanation = edu_result.get("explanation", "No analysis provided")
                    matched_education = edu_result.get("matched_education", [])
                    missing_education = edu_result.get("missing_education", [])
                except:
                    edu_score = 0.0
                    edu_explanation = "Failed to analyze education"
                    matched_education = []
                    missing_education = []

                # Step 8: Adjust weights for skills
                jd_skills = extracted_jd.get("required_technical", []) + extracted_jd.get("required_soft", [])
                if not jd_skills:
                    skills_score = 1.0
                    matched_skills = []
                    missing_skills = []
                    skills_explanation = "JD has no specific skills requirements"
                    effective_weights = section_weights.copy()
                    effective_weights["SKILLS"] = 0
                    total_other_weights = effective_weights["EXPERIENCE"] + effective_weights["EDUCATION"]
                    if total_other_weights > 0:
                        effective_weights["EXPERIENCE"] = effective_weights["EXPERIENCE"] / total_other_weights
                        effective_weights["EDUCATION"] = effective_weights["EDUCATION"] / total_other_weights
                else:
                    skills_score, matched_skills, missing_skills = get_skills_match_via_gemini(
                        extracted_resume.get("technical_skills", []),
                        extracted_resume.get("soft_skills", []),
                        extracted_jd.get("required_technical", []),
                        extracted_jd.get("required_soft", [])
                    )
                    skills_explanation = f"Matched {len(matched_skills)} of {len(jd_skills)} required skills"
                    effective_weights = section_weights

                # Step 9: Calculate overall score
                overall_score = (skills_score * effective_weights["SKILLS"] +
                                exp_score * effective_weights["EXPERIENCE"] +
                                edu_score * effective_weights["EDUCATION"]) * 100

                # Step 10: Prepare results
                result = {
                    "scores": {
                        "SKILLS": skills_score,
                        "EXPERIENCE": exp_score,
                        "EDUCATION": edu_score
                    },
                    "overall_score": overall_score,
                    "matched_skills": matched_skills,
                    "missing_skills": missing_skills,
                    "matched_education": matched_education,
                    "missing_education": missing_education,
                    "resume_total_experience": resume_exp_years,
                    "jd_min_experience": jd_min_exp,
                    "explanations": {
                        "SKILLS": skills_explanation,
                        "EXPERIENCE": exp_explanation,
                        "EDUCATION": edu_explanation
                    },
                    "selected_role": selected_role.get("role_title", "Unknown"),
                    "role_match_score": match_score
                }

                store_cache(input_hash + "_result", result)

            # Display results
            st.markdown("<div class='section-title'>📊 Match Analysis</div>", unsafe_allow_html=True)
            st.markdown(f"### 🎯 Overall Match Score: {result['overall_score']:.1f}%")
            st.markdown(f"<div class='progress-bar' style='width: {result['overall_score']}%;'>{result['overall_score']:.1f}%</div>", unsafe_allow_html=True)

            # Display selected role information
            st.markdown(f"### 👔 Selected Role: {result.get('selected_role', 'Unknown')}")
            st.info(f"Role Match Score: {result.get('role_match_score', 0):.2%}")

            # Skills breakdown
            st.markdown("### 🛠️ Skills Match")
            st.write(f"*Score:* {result['scores']['SKILLS'] * 100:.1f}%")
            if result['matched_skills']:
                st.write("✅ *Matched Skills:*")
                for match in result['matched_skills']:
                    st.markdown(f"- JD Skill: **{match['jd_skill']}** matched with CV Skill: **{match['cv_skill']}**")
            if result['missing_skills']:
                st.write("❌ *Missing Skills:* " + ", ".join(result['missing_skills']))
            st.write(f"ℹ️ {result['explanations']['SKILLS']}")

            # Experience breakdown
            st.markdown("### 💼 Experience Match")
            st.write(f"*Score:* {result['scores']['EXPERIENCE'] * 100:.1f}%")
            st.write(f"📅 *Resume Experience:* ~{result['resume_total_experience']} years")
            if result['jd_min_experience'] > 0:
                st.write(f"📌 *JD Requirement:* {result['jd_min_experience']}+ years")
            st.markdown(f"*Analysis:* {result['explanations']['EXPERIENCE']}")

            # Education breakdown
            st.markdown("### 🎓 Education Match")
            st.write(f"*Score:* {result['scores']['EDUCATION'] * 100:.1f}%")
            if result['matched_education']:
                st.write("✅ *Matched Education:* " + ", ".join(result['matched_education']))
            if result['missing_education']:
                st.write("❌ *Missing Education:* " + ", ".join(result['missing_education']))
            st.markdown(f"*Analysis:* {result['explanations']['EDUCATION']}")

elif st.button("Run Analysis"):
    st.error("Please upload a resume PDF and provide a job description.")
