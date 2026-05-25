import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGO_URI  = os.getenv("MONGO_URI")
    NLP_API_URL= os.getenv("NLP_API_URL", "https://besafev1.onrender.com/predict")
    PORT       = os.getenv("PORT")
    DEBUG      = os.getenv("DEBUG", "True") == "True"
    SECRET_KEY = os.getenv("SECRET_L=KEY")
    JWT_SECRET = os.getenv("JWT_SECRET")