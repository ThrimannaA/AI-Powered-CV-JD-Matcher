# CV_JD_comparing-and-scoring-Tool


📋 Overview

A production-level web application that intelligently matches candidate CVs with Job Descriptions using advanced AI and NLP techniques. The system evolved from using Small Language Models (SLMs) to leveraging Google's Gemini 1.5 Flash for superior contextual understanding and multi-modal parsing capabilities.

Developed during my internship at Genesiis Software for Topjobs (Sri Lanka's leading recruitment platform), this tool automates recruitment workflows by providing accurate candidate-job matching scores with detailed insights.

✨ Key Features

- Multi-format Input Support: Process PDFs, scanned images, and direct text inputs
- AI-Powered Analysis: Leverages Gemini 1.5 Flash for advanced contextual understanding
- Weighted Scoring System: Customizable scoring for:
- Skills match
- Education alignment
- Experience relevance
- Interactive Interface: Streamlit-based UI for HR teams to adjust criteria in real-time
- Multi-modal Parsing: Extracts text from both digital and scanned documents
- Detailed Insights: Provides breakdown of match percentages with explainable results

🛠️ Technology Stack

Frontend - Streamlit
Backend - Python
AI/ML Models - Gemini 1.5 Flash, all-MiniLM-L6-v2, e5-base-v2
Document Processing - PyPDF2, OCR libraries
Version Control - Git, GitHub
Project Management - JIRA
Deployment - Streamlit Cloud

🏗️ Architecture

User Input (CV/Resume + Job Description)
        ↓
[Document Processing Layer]
- PDF parsing (PyPDF2)
- Image OCR for scanned docs
- Text extraction & cleaning
        ↓
[AI Analysis Layer]
- Gemini 1.5 Flash (primary)
- Fallback: all-MiniLM-L6-v2 / e5-base-v2
- Contextual understanding
- Multi-modal parsing
        ↓
[Scoring Engine]
- Skills matching
- Education alignment
- Experience calculation
- Weighted aggregation
        ↓
[Output Layer]
- Match percentage
- Detailed breakdown
- Missing skills analysis
- Recommendations

📊 Scoring Methodology

The system employs a weighted scoring algorithm:
 - Skills Match: 40% - Technical and soft skills alignment
 - Education: 25% - Degree level, field of study relevance
 - Experience: 35% - Years and relevance of work experience

Upgrade Path: The tool was upgraded from pure SLM-based matching (all-MiniLM-L6-v2, e5-base-v2) to Gemini 1.5 Flash for:
 - Better contextual understanding of nuanced requirements
 - Improved accuracy with varied document formats
 - Enhanced multi-modal parsing capabilities

🚀 Installation & Setup

Prerequisites
-Python 3.8+
-Gemini API key
-Git

Steps
- Clone the repository
- Install dependencies
- Set up environment variables
- Run the application via streamlit run extraction.py


💡 Usage Examples

Via Streamlit Interface
- Upload CV (PDF/image) or paste text
- Enter/paste job description
- Adjust scoring weights if needed
- Click "Analyze Match"
- View detailed results and insights

📈 Sample Output

                ✨ Advanced Resume Analysing and Scoring System 📊🚀
                ====================================================================
                
                🎯 Selected Job Role for Comparison
                -----------------------------------
                Role Title: Associate Data Science/AI ML Professional
                Role Description: Entry-level data science role requiring Python, ML, and analytics skills
                Match Score: 92.00%
                
                📊 Match Analysis
                =================
                🎯 Overall Match Score: 78.5%
                [████████████████████░░░░░░░░░░░░░░░░] 78.5%
                
                👔 Selected Role: Associate Data Science/AI ML Professional
                ℹ️ Role Match Score: 92.00%
                
                🛠️ Skills Match
                ---------------
                Score: 85.0%
                
                ✅ Matched Skills:
                  • JD Skill: Python matched with CV Skill: Python
                  • JD Skill: Machine Learning matched with CV Skill: Machine Learning
                  • JD Skill: SQL matched with CV Skill: SQL
                  • JD Skill: Data Analysis matched with CV Skill: Data Analysis
                  • JD Skill: Problem Solving matched with CV Skill: Analytical Thinking
                
                ❌ Missing Skills: TensorFlow, AWS, Docker
                ℹ️ Matched 5 of 8 required skills
                
                💼 Experience Match
                ------------------
                Score: 67.0%
                📅 Resume Experience: 1.75 years
                📌 JD Requirement: 2+ years
                📋 Analysis: Resume has 1.75 years vs JD requirement of 2+ years. 
                            Score calculated as 1.75/2 = 0.875, capped at 0.67 due to 
                            relevance weighting. Relevant roles counted: Data Science 
                            Intern (0.75 years), ML Project Experience (1.0 years).
                
                🎓 Education Match
                -----------------
                Score: 90.0%
                ✅ Matched Education: BSc (Hons) in Information Technology - Specializing in Data Science
                ❌ Missing Education: None
                📋 Analysis: Education requirement fully met. BSc in Data Science matches 
                            JD requirement for Bachelor's in IT/CS field.

🔄 Development Workflow

- Followed Agile methodology with:
- Sprint planning in JIRA
- Daily standups
- Code reviews via GitHub
- Iterative development with stakeholder feedback

🏆 Key Achievements

✅ Successfully deployed for Topjobs recruitment platform
✅ Improved matching accuracy with Gemini 1.5 Flash upgrade
✅ Reduced manual CV screening time by approximately 70%
✅ Handled 100+ CVs during testing phase
✅ Received positive feedback during the testing phase

🔮 Future Enhancements

Add support for more document formats (DOCX, RTF)

- Implement batch processing for multiple CVs
- Add candidate ranking dashboard
- Add more language model options
- Implement feedback loop for continuous improvement

📝 License

This project was developed during my internship at Genesiis Software for Topjobs.

📧 Contact

Anuji Thrimanna
Email: thrimanna2000@gmail.com
LinkedIn: https://www.linkedin.com/in/anuji-thrimanna-6389392a9/

⭐ If you find this project useful, please consider giving it a star on GitHub!
