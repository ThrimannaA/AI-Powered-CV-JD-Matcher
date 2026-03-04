# the new application and this is working but some of test features are not available here... I uploaded video to GITHUB based on this code 

import streamlit as st
from google import genai
import os
import io
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re
import logging
from typing import Optional, List, Dict, Any
from PIL import Image
from pdf2image import convert_from_bytes
import base64


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


client = genai.Client()   # reads GOOGLE_API_KEY from env automatically

def get_gemini_response(input_text: str, image: Optional[Image.Image] = None) -> Optional[str]:
    try:
        contents = [input_text]
        if image is not None:
            contents.append(image)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=genai.types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=4096,
            )
        )

        text = response.text.strip()

        # Common post-processing
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
        text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
        text = re.sub(r',\s*([\}\]])', r'\1', text)

        return text

    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None
    
    
# --- Helper Functions ---
def get_today_date() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def get_daily_request_count() -> int:
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    c.execute("SELECT count FROM request_logs WHERE date = ?", (get_today_date(),))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_request_count():
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    today = get_today_date()
    count = get_daily_request_count()
    if count == 0:
        c.execute("INSERT INTO request_logs (date, count) VALUES (?, ?)", (today, 1))
    else:
        c.execute("UPDATE request_logs SET count = ? WHERE date = ?", (count + 1, today))
    conn.commit()
    conn.close()

# def get_gemini_response(input_text, image=None):
#     try:
#         response_text = get_gemini_response(input_text, image)
#         if response_text:
#             return response_text
#         else:
#             logger.error("No valid response from Vertex AI")
#             return None
#     except Exception as e:
#         logger.error(f"Error with Vertex AI request: {e}")
#         return None

def input_file_text(uploaded_file) -> str:
    if not uploaded_file:
        return ""

    ext = uploaded_file.name.split('.')[-1].lower()
    logger.info(f"Processing file: {uploaded_file.name}  ({ext})")

    prompt = ("Extract all text accurately. Preserve formatting, line breaks, structure. "
              "Handle mixed languages (English, Tamil, Sinhala) correctly. Return plain text.")

    content = uploaded_file.getvalue()

    if ext == 'pdf':
        try:
            poppler_path = r"C:\Poppler\poppler-25.07.0\Library\bin"  # ← adjust if needed
            images = convert_from_bytes(content, poppler_path=poppler_path)
            extracted = []
            for i, img in enumerate(images, 1):
                logger.info(f"PDF page {i}")
                text = get_gemini_response(prompt, img)
                if text:
                    extracted.append(text)
            full_text = "\n".join(extracted)
            logger.info(f"PDF extracted: {len(full_text)} chars")
            return normalize_text(full_text)
        except Exception as e:
            logger.error(f"PDF error: {e}")
            return ""

    elif ext in ['docx']:
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            raw = "\n".join(p.text for p in doc.paragraphs)
            resp = get_gemini_response(f"{prompt}\n\n{raw}")
            return normalize_text(resp if resp else raw)
        except:
            return ""

    elif ext == 'doc':
        try:
            import docx2txt
            raw = docx2txt.process(io.BytesIO(content))
            resp = get_gemini_response(f"{prompt}\n\n{raw}")
            return normalize_text(resp if resp else raw)
        except:
            return ""

    elif ext == 'txt':
        try:
            raw = content.decode('utf-8', errors='replace')
            resp = get_gemini_response(f"{prompt}\n\n{raw}")
            return normalize_text(resp if resp else raw)
        except:
            return ""

    elif ext == 'odt':
        try:
            from odf import text, teletype
            from odf.opendocument import load
            doc = load(io.BytesIO(content))
            raw = ""
            for el in doc.getElementsByType(text.P):
                raw += teletype.extractText(el) + "\n"
            resp = get_gemini_response(f"{prompt}\n\n{raw}")
            return normalize_text(resp if resp else raw)
        except:
            return ""

    else:
        logger.warning(f"Unsupported format: {ext}")
        return ""

def normalize_text(txt):
    logger.info("Normalizing text")
    txt = re.sub(r'[^\w\s\.\-]', ' ', txt)  # Keep only words, spaces, dots, and hyphens
    txt = re.sub(r'\s+', ' ', txt)  # Replace multiple spaces with single space
    normalized = txt.strip()  # Remove leading spaces
    logger.info(f"Text normalized. Original length: {len(txt)}, Normalized length: {len(normalized)}")
    return normalized

def extract_text_from_image(image: Image.Image) -> str:
    prompt = "Extract all text from this image accurately. Preserve formatting, line breaks, structure."
    resp = get_gemini_response(prompt, image)
    return resp if resp else ""

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
def detect_language(text: str) -> str:
    if not text.strip():
        return "Unknown"
    prompt = f"Detect primary language. Return only name (English, Tamil, Sinhala, ...):\n\n{text[:1500]}"
    resp = get_gemini_response(prompt)
    return resp.strip() if resp else "Unknown"

def translate_to_english(text: str) -> str:
    if not text.strip():
        return text
    prompt = "Translate to English. Preserve meaning, structure, job details:\n\n" + text
    resp = get_gemini_response(prompt)
    return resp if resp else text

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

def normalize_text(txt: str) -> str:
    txt = re.sub(r'[^\w\s\.\-]', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()

def hash_input(resume_text: str, jd_text: str, weights: dict) -> str:
    combined = (normalize_text(resume_text) + "||" +
                normalize_text(jd_text) + "||" +
                json.dumps(weights, sort_keys=True)).encode('utf-8')
    return hashlib.sha256(combined).hexdigest()

def check_cache(key: str) -> Optional[Dict]:
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    c.execute("SELECT result FROM results_cache WHERE input_hash = ?", (key,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def store_cache(key: str, data: Any):
    conn = sqlite3.connect('cache.db')
    c = conn.cursor()
    timestamp = datetime.utcnow().isoformat()
    c.execute("INSERT OR REPLACE INTO results_cache (input_hash, result, timestamp) VALUES (?, ?, ?)",
              (key, json.dumps(data), timestamp))
    conn.commit()
    conn.close()

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
        response_text = get_gemini_response(input_text)
        
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

st.set_page_config(page_title="ATS Resume Analyzer", layout="wide")
st.header("✨ Advanced Resume Analysing and Scoring System 📊🚀")

# Sidebar quota
st.sidebar.markdown("### Gemini API Usage")
used = get_daily_request_count()
max_limit = 50
st.sidebar.progress(min(used / max_limit, 1.0), text=f"{used}/{max_limit} today")

# ── Inputs ───────────────────────────────────────

st.subheader("Provide Job Description")

col1, col2 = st.columns(2)

with col1:
    jd_text = st.text_area("Paste Job Description (optional)", height=300)

with col2:
    jd_images = st.file_uploader(
        "Upload JD Images (PNG/JPG/JPEG, multiple allowed)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

jd = jd_text.strip()

# Process JD images
if jd_images:
    extracted = []
    for idx, f in enumerate(jd_images, 1):
        try:
            img = Image.open(f)
            txt = extract_text_from_image(img)
            if txt:
                extracted.append(txt)
        except Exception as e:
            st.warning(f"Image {idx} failed: {e}")
    if extracted:
        jd_from_images = "\n---\n".join(extracted).strip()
        if jd:
            jd += "\n\n" + jd_from_images
        else:
            jd = jd_from_images

# Language handling
if jd:
    lang = detect_language(jd)
    st.info(f"Detected JD language: {lang}")
    if lang.lower() != "english":
        jd = translate_to_english(jd)
    st.markdown("### Extracted / Translated JD")
    st.markdown(f"<div style='border:1px solid #ccc; padding:12px; white-space:pre-wrap'>{jd}</div>", unsafe_allow_html=True)

# Resume
with col2:
    resume_file = st.file_uploader("Upload Candidate Resume", type=["pdf","docx","doc","txt","odt"])

resume_text = ""
if resume_file:
    if 'last_file' not in st.session_state or st.session_state.last_file != resume_file:
        st.session_state.last_file = resume_file
        st.session_state.resume_text = input_file_text(resume_file)
    resume_text = st.session_state.resume_text

    st.markdown("### Extracted Resume Text")
    st.markdown(f"<div style='border:1px solid #ccc; padding:12px; white-space:pre-wrap'>{resume_text}</div>", unsafe_allow_html=True)

# Weights
st.subheader("Evaluation Weights")
c1, c2, c3 = st.columns(3)
with c1: skills_w = st.slider("Skills (%)", 0, 100, 50)
with c2: exp_w   = st.slider("Experience (%)", 0, 100, 30)
with c3: edu_w   = st.slider("Education (%)", 0, 100, 20)

if skills_w + exp_w + edu_w != 100:
    st.error("Weights must sum to 100%")
    st.stop()

weights = {
    "SKILLS": skills_w / 100,
    "EXPERIENCE": exp_w / 100,
    "EDUCATION": edu_w / 100
}

# ── Run Analysis ─────────────────────────────────

if resume_text and jd and st.button("🔍 Run Comprehensive Analysis", type="primary"):

    input_hash = hash_input(resume_text, jd, weights)
    cached = check_cache(input_hash + "_result")

    if cached:
        result = cached
        st.info("Using cached result")
    else:
        with st.spinner("Full analysis in progress... (may take 30–90 seconds)"):

            # Identify roles → select best → extract requirements
            job_roles = identify_job_roles(jd)
            best_idx, role_match_score = find_best_matching_role(resume_text, job_roles)
            selected_role = job_roles[best_idx]

            jd_req = extract_role_specific_requirements(jd, best_idx, job_roles)

            resume_req = extract_resume_requirements(resume_text)

            # Skills
            skills_score, matched_sk, missing_sk = get_skills_match_via_gemini(
                resume_req.get("technical_skills", []),
                resume_req.get("soft_skills", []),
                jd_req.get("required_technical", []),
                jd_req.get("required_soft", [])
            )

            # Experience
            current_date = datetime.now().strftime("%Y-%m-%d")
            exp_prompt = input_prompt_experience.format(
                current_date=current_date,
                resume_experience=json.dumps(resume_req.get("experience", [])),
                jd_experience=json.dumps(jd_req.get("experience", []))
            )
            exp_raw = get_gemini_response(exp_prompt)
            try:
                exp_data = json.loads(exp_raw)
                exp_score = exp_data.get("score", 0.0)
            except:
                exp_score = 0.0

            # Education
            edu_prompt = input_prompt_education.format(
                resume_education=json.dumps(resume_req.get("education", [])),
                jd_education=json.dumps(jd_req.get("education", []))
            )
            edu_raw = get_gemini_response(edu_prompt)
            try:
                edu_data = json.loads(edu_raw)
                edu_score = edu_data.get("score", 0.0)
            except:
                edu_score = 0.0

            # Final score
            overall = (
                skills_score * weights["SKILLS"] +
                exp_score   * weights["EXPERIENCE"] +
                edu_score   * weights["EDUCATION"]
            ) * 100

            result = {
                "overall_score": overall,
                "scores": {"SKILLS": skills_score, "EXPERIENCE": exp_score, "EDUCATION": edu_score},
                "selected_role": selected_role.get("role_title", "Unknown"),
                "role_match_score": role_match_score,
                # ... add more fields you want to display
            }

            store_cache(input_hash + "_result", result)

    # ── Display Result ───────────────────────────────────────

    st.markdown(f"### Overall Match Score: **{result['overall_score']:.1f}%**")
    st.progress(result['overall_score'] / 100)
    st.info(f"Best matching role: **{result['selected_role']}** ({result['role_match_score']:.0%} role fit)")

    # You can expand this section with matched/missing skills, explanations, etc.

else:
    if not (resume_text and jd):
        st.info("Please upload resume + provide job description to start analysis.")