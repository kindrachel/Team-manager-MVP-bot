from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, BigInteger, Text, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone as tz
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Index 
from enum import Enum as PythonEnum
import enum
import pytz

Base = declarative_base()

from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Index, create_engine
from enum import Enum as PythonEnum
import enum
import pytz

Base = declarative_base()

class UserRole(enum.Enum):
    MEMBER = "MEMBER"
    TRAINER = "TRAINER"
    SUPER_ADMIN = "SUPER_ADMIN" 
    ORG_ADMIN = "ORG_ADMIN" 

class MessageScheduleStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"

class ChallengeStatus(enum.Enum):
    PENDING = "PENDING"         
    ACTIVE = "ACTIVE"           
    COMPLETED = "COMPLETED"   
    FAILED = "FAILED"         
    SCHEDULED = "SCHEDULED"    
    OFFERED = "OFFERED"

class SurveyType(PythonEnum):
    MORNING = "morning"    # Утренний опрос (6:00 - 12:00)
    AFTERNOON = "afternoon"  # Дневной опрос (12:00 - 18:00)  
    EVENING = "evening"    # Вечерний опрос (18:00 - 22:00)

class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    org_type = Column(String(50), nullable=False)
    admin_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    timezone = Column(String(50), default="Asia/Novosibirsk")
    
    users = relationship("User", back_populates="organization")
    message_schedules = relationship("MessageSchedule", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    chat_id = Column(BigInteger)
    org_id = Column(Integer, ForeignKey('organizations.id'))
    
    name = Column(String(255))
    phone = Column(String(20))
    direction = Column(String(50))
    sport_type = Column(String(50))
    position = Column(String(255))
    profile_photo_path = Column(String(255), nullable=True)
    has_custom_photo = Column(Boolean, default=False)
    
    role = Column(String(50), default=UserRole.MEMBER.value)

    trainer_verified = Column(Boolean, default=False)  
    verification_requested_at = Column(DateTime, nullable=True)  
    verified_at = Column(DateTime, nullable=True)  
    verified_by = Column(BigInteger, ForeignKey('users.user_id'), nullable=True) 
    
    points = Column(Integer, default=0)
    level = Column(Integer, default=1)
    energy = Column(Integer)
    sleep_quality = Column(Integer)
    readiness = Column(Integer)
    mood = Column(String(50))
    
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime)
    
    registered_at = Column(DateTime, default=lambda: datetime.now(tz.utc))
    last_survey_at = Column(DateTime, nullable=True)
    last_survey_type = Column(String(20), nullable=True)
    last_active = Column(DateTime, default=datetime.now)

    message_logs = relationship("MessageSentLog", back_populates="user", cascade="all, delete-orphan")
    organization = relationship("Organization", back_populates="users")
    surveys = relationship("Survey", back_populates="user", cascade="all, delete-orphan")
    metrics_surveys = relationship("MetricsSurvey", back_populates="user", cascade="all, delete-orphan")
    challenges = relationship("Challenge", back_populates="user_rel", foreign_keys="[Challenge.user_id]")
    created_challenges = relationship("Challenge", back_populates="creator_rel", foreign_keys="[Challenge.created_by]")
    verifier = relationship("User", foreign_keys=[verified_by], remote_side=[user_id])

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name}, role={self.role})>"

    def get_effective_role(self):
        """Получить фактическую роль с учетом верификации"""
        if self.role == UserRole.TRAINER.value and not self.trainer_verified:
            return UserRole.MEMBER.value
        return self.role
    
    @property
    def is_verified_trainer(self):
        """Проверка, является ли пользователь верифицированным тренером"""
        return self.role == UserRole.TRAINER.value and self.trainer_verified

class Survey(Base):
    __tablename__ = "surveys"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'))
    survey_type = Column(String(20))
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    energy = Column(Integer)
    sleep = Column(Integer)
    readiness = Column(Integer)
    mood = Column(String(50))
    answers = Column(String(1000))

    # Для хранения данных AI-опросов и результатов ProffKonstalting
    survey_data = Column(JSONB, nullable=True)

    user = relationship("User", back_populates="surveys")


class MetricsSurvey(Base):
    """Модель для хранения результатов AI-опросов по метрикам ProffKonstalting"""
    __tablename__ = "metrics_surveys"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)

    # Тип опроса: 'single' (по одной метрике) или 'full' (полный опрос)
    survey_type = Column(String(20), nullable=False)

    # Ключ метрики (для одиночных опросов)
    metric_key = Column(String(50), nullable=True)

    # Структурированные данные опроса
    responses = Column(JSONB, nullable=True)  # Ответы пользователя
    results = Column(JSONB, nullable=True)    # Результаты анализа
    overall_score = Column(Integer, nullable=True)  # Общий балл (0-100)
    category = Column(String(50), nullable=True)    # Категория профиля

    # Флаги и контекст
    ai_generated = Column(Boolean, default=True)  # Сгенерирован ИИ
    user_context = Column(JSONB, nullable=True)   # Контекст пользователя

    # Временные метки
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Отношения
    user = relationship("User", back_populates="metrics_surveys")

    # Индексы для производительности
    __table_args__ = (
        Index('idx_metrics_survey_user_type', 'user_id', 'survey_type'),
        Index('idx_metrics_survey_created', 'created_at'),
        Index('idx_metrics_survey_metric', 'metric_key'),
    )


class Challenge(Base):
    __tablename__ = "challenges"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id')) 
    created_by = Column(BigInteger, ForeignKey('users.user_id')) 
    text = Column(String(500), nullable=False)
    status = Column(String(20), default=ChallengeStatus.PENDING.value)
    points = Column(Integer, default=10)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)
    is_custom = Column(Boolean, default=False)

    scheduled_for = Column(DateTime, nullable=True)  
    sent_at = Column(DateTime, nullable=True)        
    challenge_time = Column(String(20), nullable=True) 

    difficulty = Column(String(20), nullable=True)     
    duration = Column(String(50), nullable=True)        
    focus_area = Column(String(100), nullable=True)    

    user_rel = relationship("User", foreign_keys=[user_id], back_populates="challenges")
    creator_rel = relationship("User", foreign_keys=[created_by], back_populates="created_challenges")



class PendingChallenge(Base):
    """Временное хранилище сгенерированных челленджей"""
    __tablename__ = "pending_challenges"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)  
    org_id = Column(Integer, nullable=False)    
    chat_id = Column(BigInteger, nullable=False)  
    
    challenges = Column(JSONB, nullable=False)   
    status = Column(String(20), default="PENDING")  
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False) 

    __table_args__ = (
        Index('idx_pending_user_id', 'user_id'),
        Index('idx_pending_expires', 'expires_at'),
        Index('idx_pending_status', 'status'),
    )
    
    def is_expired(self):
        """Проверка истечения срока жизни"""
        return datetime.now(timezone.utc) > self.expires_at


class MessageSchedule(Base):
    """Расписание автоматических сообщений"""
    __tablename__ = "message_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    scheduled_time = Column(Time, nullable=False)  # Время отправки (часы:минуты)
    message_type = Column(String(50), nullable=False)  # morning_greeting, training_reminder и т.д.
    status = Column(String(20), default=MessageScheduleStatus.ACTIVE.value)
    is_daily = Column(Boolean, default=True)  # Ежедневное сообщение
    day_of_week = Column(Integer, nullable=True)  # 0-6 (пн-вс), если не ежедневное
    order_index = Column(Integer, default=0)  # Порядок отображения
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    organization = relationship("Organization", back_populates="message_schedules")
    sent_logs = relationship("MessageSentLog", back_populates="schedule", cascade="all, delete-orphan")
    
class MessageSentLog(Base):
    """Лог отправленных сообщений"""
    __tablename__ = "message_sent_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("message_schedules.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(20), default="sent")  # sent, failed, pending
    error_message = Column(Text, nullable=True)
    
    # Отношения
    schedule = relationship("MessageSchedule", back_populates="sent_logs")
    user = relationship("User", back_populates="message_logs")


class PlayerMetrics(Base):
    """Метрики оценки игрока"""
    __tablename__ = "player_metrics"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)
    coach_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    
    # Технические характеристики (1-10)
    short_pass = Column(Integer, nullable=True)  # Короткий пас
    first_touch = Column(Integer, nullable=True)  # Первый контакт (касание)
    long_pass = Column(Integer, nullable=True)    # Дальний пас
    positioning = Column(Integer, nullable=True)  # Выбор позиции
    aerobic_game = Column(Integer, nullable=True) # Аэробная игра (защита)
    heading = Column(Integer, nullable=True)      # Удар головой
    ball_fighting = Column(Integer, nullable=True) # Навыки борьбы за мяч
    
    # Физические характеристики (1-10)
    strength = Column(Integer, nullable=True)     # Сила
    flexibility = Column(Integer, nullable=True)  # Гибкость
    balance = Column(Integer, nullable=True)      # Баланс
    speed = Column(Integer, nullable=True)        # Скорость
    stamina = Column(Integer, nullable=True)      # Выносливость
    agility = Column(Integer, nullable=True)      # Ловкость
    
    # Ментальные характеристики (1-10)
    attention = Column(Integer, nullable=True)    # Внимание
    analytical_thinking = Column(Integer, nullable=True)  # Аналитическое мышление
    positioning_sense = Column(Integer, nullable=True)    # Позиционирование
    communication = Column(Integer, nullable=True)        # Общение
    teamwork = Column(Integer, nullable=True)             # Работа в команде
    concentration = Column(Integer, nullable=True)        # Концентрация
    leadership = Column(Integer, nullable=True)           # Лидерство
    game_excitement = Column(Integer, nullable=True)      # Волнение в игре
    
    notes = Column(Text, nullable=True)  # Комментарии тренера
    assessment_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    # Отношения
    player = relationship("User", foreign_keys=[player_id])
    coach = relationship("User", foreign_keys=[coach_id])
    organization = relationship("Organization")
    
    def get_technical_average(self):
        """Средняя оценка технических характеристик"""
        tech_scores = [
            self.short_pass, self.first_touch, self.long_pass,
            self.positioning, self.aerobic_game, self.heading, self.ball_fighting
        ]
        valid_scores = [s for s in tech_scores if s is not None]
        return round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None
        
    def get_physical_average(self):
        """Средняя оценка физических характеристик"""
        phys_scores = [
            self.strength, self.flexibility, self.balance,
            self.speed, self.stamina, self.agility
        ]
        valid_scores = [s for s in phys_scores if s is not None]
        return round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None

    def get_mental_average(self):
        """Средняя оценка ментальных характеристик"""
        mental_scores = [
            self.attention, self.analytical_thinking, self.positioning_sense,
            self.communication, self.teamwork, self.concentration,
            self.leadership, self.game_excitement
        ]
        valid_scores = [s for s in mental_scores if s is not None]
        return round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None

    def get_overall_average(self):
        """Общая средняя оценка"""
        averages = []
        tech_avg = self.get_technical_average()
        phys_avg = self.get_physical_average()
        mental_avg = self.get_mental_average()
        
        if tech_avg: averages.append(tech_avg)
        if phys_avg: averages.append(phys_avg)
        if mental_avg: averages.append(mental_avg)
        
        return round(sum(averages) / len(averages), 1) if averages else None
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('idx_metrics_player_date', 'player_id', 'assessment_date'),
        Index('idx_metrics_coach', 'coach_id'),
        Index('idx_metrics_org', 'org_id'),
    )