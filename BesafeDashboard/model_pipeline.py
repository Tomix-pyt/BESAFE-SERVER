import numpy as np
import re
import onnxruntime as ort
from keras_preprocessing.text import tokenizer_from_json

MODEL_VERSION = '1.0.00'
TOKENIZER_PATH= 'tokenizers/BesafeV1_1.0.00.json'
ONNX ='model/BesafeV1_1.0.00.onnx'

# LOADING TOKENIZER
with open(TOKENIZER_PATH) as f:
    tokenizer = tokenizer_from_json(f.read())

# LOADING ONXX MODEL
session = ort.InferenceSession(ONNX)
input_name = session.get_inputs()[0].name

# SPECIFYING MAX NO: OF WORDS TO USE (must match the ones used during training)
MAX_LEN = 100 

# CLEANING 
def clean_text(text):
    # Convert to string
    text = str(text)
    # Remove URLs, mentions, special characters (keep letters and spaces)
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'[^a-zA-Z\s\u0600-\u06FF]', '', text)  # Keep English/Arabic letters
    text = text.lower()
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# PADDING WITH NUMPY
def pad_sequences(sequences, maxlen):
    padded = np.zeros((len(sequences), maxlen),dtype=np.int32)
    
    for i, seq in enumerate(sequences):
        seq = seq[:maxlen]
        padded[i, :len(seq)] = seq
        
    return padded


# PREPROCESSES 

def preprocess( text):
    cleaned = clean_text(text)
    seq = tokenizer.texts_to_sequences([cleaned])
    vec = pad_sequences(seq,MAX_LEN)
    return vec


# PREDICTION
def predict_threat(text,threshold=0.5):
    processed = preprocess(text=text)
    confidecnce = session.run(None,{input_name:processed})
    confidecnce = confidecnce[0][0][0]
    confidecnce =round(float(confidecnce), 2)
    label = int(confidecnce > threshold)
    label = "Threat" if label == 1 else "Non-Threat"
    return label, confidecnce,MODEL_VERSION
