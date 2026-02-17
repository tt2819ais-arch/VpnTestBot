from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()
engine = create_engine('sqlite:///users.db')
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    first_name = Column(String)
    udid = Column(String, nullable=True)  # UDID iPhone
    uuid = Column(String, nullable=True)  # Сгенерированный UUID для VLESS
    is_authorized = Column(Boolean, default=False)
    registered_at = Column(DateTime, default=datetime.datetime.now)
    last_active = Column(DateTime, default=datetime.datetime.now)

class BotConfig(Base):
    __tablename__ = 'bot_config'
    
    id = Column(Integer, primary_key=True)
    vpn_password = Column(String, default="a7F9k2Pq4LmX")
    help_text = Column(String, default="Инструкция по подключению...")

Base.metadata.create_all(engine)
