from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password = Column(String(256), nullable=False)
    is_admin = Column(Boolean, default=False)

class Delivery(Base):
    __tablename__ = 'deliveries'
    id = Column(Integer, primary_key=True)
    address = Column(String(300), nullable=False)
    city = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def get_engine_and_session(path='sqlite:///otimizador_railway.db'):
    engine = create_engine(path, echo=False)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    return engine, Session
