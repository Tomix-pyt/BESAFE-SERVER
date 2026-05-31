import certifi
from pymongo import MongoClient
from config import Config

client = MongoClient(Config.MONGO_URI, tlsCAFile=certifi.where())
besafe_client = client.get_database('BesafeDB')
