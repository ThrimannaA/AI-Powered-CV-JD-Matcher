# CV_JD_comparing-and-scoring-Tool


📋 Overview

A production-level web application that intelligently matches candidate CVs with Job Descriptions using advanced AI and NLP techniques. Originally developed at Genesiis Software using Gemini 2.5 Flash (paid version), the system now features intelligent model fallback to work within free quota limits while maintaining high accuracy.

Developed during my internship at Genesiis Software for Topjobs (Sri Lanka's leading recruitment platform), this tool automates recruitment workflows by providing accurate candidate-job matching scores with detailed insights.

✨ Key Features

- Multi-format Input Support: Process PDFs, scanned images, and direct text inputs
- AI-Powered Analysis: Leverages multiple AI models with intelligent fallback (Gemini 2.5 Flash Lite, Gemma 3 27B) for advanced contextual understanding within free quota limits
- Weighted Scoring System: Customizable scoring for:
- Skills match
- Education alignment
- Experience relevance
- Interactive Interface: Streamlit-based UI for HR teams to adjust criteria in real-time
- Multi-modal Parsing: Extracts text from both digital and scanned documents
- Detailed Insights: Provides breakdown of match percentages with explainable results

🛠️ Technology Stack

- Frontend - Streamlit
- Backend - Python
- AI/ML Models - Gemini 2.5 Flash Lite, Gemma 3 27B, Gemini 2.5 Flash (legacy), all-MiniLM-L6-v2, e5-base-v2
- Document Processing - PyPDF2, OCR libraries
- Version Control - Git, GitHub
- Project Management - JIRA
- Deployment - Streamlit Cloud

🏗️ Architecture

User Input (CV/Resume + Job Description)
        ↓
[Document Processing Layer]
- PDF parsing (PyPDF2)
- Image OCR for scanned docs
- Text extraction & cleaning
        ↓
[AI Analysis Layer]
- Gemini 2.5 Flash Lite (primary - 20 RPD)
- Fallback Chain:
   - Gemma 3 27B (14,400 RPD - unlimited free tier)
   - Gemini 2.5 Flash (legacy support)
   - all-MiniLM-L6-v2 / e5-base-v2 (local fallback)
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

The system employs a default weighted scoring algorithm:
 - Skills Match: 50% - Technical and soft skills alignment
 - Education: 30% - Degree level, field of study relevance
 - Experience: 20% - Years and relevance of work experience

Model Evolution:
-Phase 1 (Internship - Paid): Gemini 2.5 Flash for production deployment at Topjobs
-Phase 2 (Current - Free Quota): Multi-model fallback system with Gemma 3 27B handling 14,400 requests/day
-Benefits of current architecture:
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

📌 Note on Model Configuration:
The app now features intelligent model fallback to work within free quota limits:
- Primary: Gemini 2.5 Flash Lite (20 requests/day)
- Fallback: Gemma 3 27B (14,400 requests/day - effectively unlimited)
No API key configuration needed for Gemma models - they work with the same Gemini API key!

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

- Successfully deployed for Topjobs recruitment platform
- Improved matching accuracy with Gemini models during paid internship phase
- Implemented intelligent model fallback system to work within free quota limits (14,400 requests/day with Gemma 3 27B)
- Reduced manual CV screening time by approximately 70%
- Handled 100+ CVs during testing phase
- Received positive feedback during the testing phase

🔮 Future Enhancements

- Add support for more document formats (DOCX, RTF)
- Implement batch processing for multiple CVs
- Add candidate ranking dashboard
- Add more language model options
- Implement feedback loop for continuous improvement

📝 License

This project was developed during my internship at Genesiis Software for Topjobs.

📌 **Development Note:** 
This project was initially developed during my internship at Genesiis Software using Gemini 2.5 Flash (paid version) for Topjobs. The current version has been enhanced with intelligent model fallback to work within free quota limits while maintaining the same level of accuracy and functionality.

📧 Contact

- Email: thrimanna2000@gmail.com
- LinkedIn: https://www.linkedin.com/in/anuji-thrimanna-6389392a9/

⭐ If you find this project useful, please consider giving it a star on GitHub!
