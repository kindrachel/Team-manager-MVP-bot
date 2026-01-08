from datetime import datetime, timezone, timedelta
from sqlalchemy import func, and_
from database import User, Survey, Challenge, Organization, get_session, SurveyType, ChallengeStatus
from typing import Dict, List, Tuple
import pytz

class MetricsCollector:
    """Сбор и анализ метрик активности пользователей"""
    
    @staticmethod
    def get_user_stats(user_id: int) -> dict:
        """Получить статистику пользователя"""
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return None
            
            nsk_tz = pytz.timezone('Asia/Novosibirsk')
            now_nsk = datetime.now(nsk_tz)
            
            total_surveys = session.query(Survey).filter(Survey.user_id == user.id).count()
            completed_challenges = session.query(Challenge).filter(
                Challenge.user_id == user.id,
                Challenge.status == ChallengeStatus.COMPLETED.value
            ).count()
            pending_challenges = session.query(Challenge).filter(
                Challenge.user_id == user.id,
                Challenge.status == ChallengeStatus.PENDING.value
            ).count()
            
            if total_surveys > 0:
                avg_energy = session.query(func.avg(Survey.energy)).filter(Survey.user_id == user.id).scalar() or 0
                avg_sleep = session.query(func.avg(Survey.sleep)).filter(Survey.user_id == user.id).scalar() or 0
                avg_readiness = session.query(func.avg(Survey.readiness)).filter(Survey.user_id == user.id).scalar() or 0
            else:
                avg_energy = 0
                avg_sleep = 0
                avg_readiness = 0
            
            if total_surveys > 0 and user.registered_at:
                if user.registered_at.tzinfo is None:
                    registered_at_nsk = nsk_tz.localize(user.registered_at)
                else:
                    registered_at_nsk = user.registered_at.astimezone(nsk_tz)
                
                days_active = (now_nsk - registered_at_nsk).days + 1
                attendance_percent = min(int((total_surveys / days_active) * 100), 100) if days_active > 0 else 0
            else:
                attendance_percent = 0
            
            today_start_nsk = now_nsk.replace(hour=0, minute=0, second=0, microsecond=0)
            
            today_start_utc = today_start_nsk.astimezone(timezone.utc)
            
            today_surveys = session.query(Survey).filter(
                Survey.user_id == user.id,
                Survey.date >= today_start_utc
            ).count()
            
            today_completed = session.query(Challenge).filter(
                Challenge.user_id == user.id,
                Challenge.status == ChallengeStatus.COMPLETED.value,
                Challenge.completed_at >= today_start_utc
            ).count()
            
            return {
                'total_surveys': total_surveys,
                'completed_challenges': completed_challenges,
                'pending_challenges': pending_challenges,
                'avg_energy': round(avg_energy, 1),
                'avg_sleep': round(avg_sleep, 1),
                'avg_readiness': round(avg_readiness, 1),
                'attendance_percent': attendance_percent,
                'today_surveys': today_surveys,
                'today_completed_challenges': today_completed
            }
        finally:
            session.close()

    
    @staticmethod
    def get_organization_stats(org_id: int) -> Dict:
        """Получить статистику по организации"""
        session = get_session()
        try:
            org = session.query(Organization).filter(Organization.id == org_id).first()
            if not org:
                return {}
            
            users = session.query(User).filter(User.org_id == org_id).all()
            
            if not users:
                return {
                    "org_name": org.name,
                    "total_members": 0,
                    "total_surveys": 0,
                    "avg_level": 0,
                    "total_points": 0
                }
            
            total_surveys = session.query(func.count(Survey.id)).filter(
                Survey.user_id.in_([u.id for u in users])
            ).scalar()
            
            avg_level = session.query(func.avg(User.level)).filter(
                User.org_id == org_id
            ).scalar() or 0
            
            total_points = session.query(func.sum(User.points)).filter(
                User.org_id == org_id
            ).scalar() or 0
            
            completed_challenges = session.query(func.count(Challenge.id)).filter(
                and_(
                    Challenge.user_id.in_([u.id for u in users]),
                    Challenge.status == ChallengeStatus.COMPLETED.value
                )
            ).scalar()
            
            return {
                "org_name": org.name,
                "org_type": org.org_type,
                "total_members": len(users),
                "total_surveys": total_surveys,
                "avg_level": round(avg_level, 1),
                "total_points": total_points,
                "completed_challenges": completed_challenges,
                "members": [MetricsCollector.get_user_stats(u.user_id) for u in users]
            }
        finally:
            session.close()
    
    @staticmethod
    def get_leaderboard(org_id: int, limit: int = 10) -> List[Tuple]:
        """Получить лидерборд по очкам"""
        session = get_session()
        try:
            leaderboard = session.query(User).filter(
                User.org_id == org_id
            ).order_by(User.points.desc()).limit(limit).all()
            
            result = []
            for idx, user in enumerate(leaderboard, 1):
                result.append({
                    "position": idx,
                    "name": user.name,
                    "points": user.points,
                    "level": user.level,
                    "position_role": user.position
                })
            return result
        finally:
            session.close()
    
    @staticmethod
    def get_daily_report(org_id: int) -> Dict:
        """Ежедневный отчет"""
        session = get_session()
        try:
            # Часовой пояс Новосибирска
            nsk_tz = pytz.timezone('Asia/Novosibirsk')
            
            # Начало и конец дня в Новосибирске
            today_start_nsk = datetime.now(nsk_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            today_end_nsk = today_start_nsk + timedelta(days=1)
            
            # Конвертируем в UTC для запросов к БД
            today_start_utc = today_start_nsk.astimezone(timezone.utc)
            today_end_utc = today_end_nsk.astimezone(timezone.utc)
            
            users = session.query(User).filter(User.org_id == org_id).all()
            
            today_surveys = session.query(Survey).filter(
                and_(
                    Survey.user_id.in_([u.id for u in users]),
                    Survey.date >= today_start_utc,
                    Survey.date < today_end_utc
                )
            ).all()
            
            completed_challenges = session.query(Challenge).filter(
                and_(
                    Challenge.user_id.in_([u.id for u in users]),
                    Challenge.status == ChallengeStatus.COMPLETED.value,
                    Challenge.completed_at >= today_start_utc,
                    Challenge.completed_at < today_end_utc
                )
            ).count()
            
            # Исправляем вычисление avg_energy
            surveys_with_energy = [s for s in today_surveys if s.energy is not None]
            avg_energy = sum([s.energy for s in surveys_with_energy]) / len(surveys_with_energy) if surveys_with_energy else 0
            
            return {
                "date": today_start_nsk.strftime("%d.%m.%Y"),
                "total_users": len(users),
                "active_users": len(set([s.user_id for s in today_surveys])),
                "total_surveys_today": len(today_surveys),
                "completed_challenges": completed_challenges,
                "avg_energy": round(avg_energy, 1),
                "survey_response_rate": round((len(set([s.user_id for s in today_surveys])) / len(users) * 100) if users else 0, 1)
            }
        finally:
            session.close()
    
    @staticmethod
    def record_survey(user_db_id: int, survey_type: str, energy: int, sleep: int, readiness: int, mood: str) -> bool:
        """Сохранить опрос в историю"""
        import traceback
        
        try:
            print(f"\n📥 METRICS COLLECTOR: record_survey called")
            print(f"   user_db_id: {user_db_id}")
            print(f"   survey_type: {survey_type}")
            print(f"   energy: {energy}, sleep: {sleep}, readiness: {readiness}, mood: {mood}")
            
            session = get_session()
            
            user = session.query(User).filter(User.id == user_db_id).first()
            if not user:
                print(f"❌ User with DB ID {user_db_id} not found!")
                session.close()
                return False
            
            print(f"✅ User found: {user.name} (Telegram ID: {user.user_id})")
            
            survey = Survey(
                user_id=user_db_id,
                survey_type=survey_type,
                energy=energy,
                sleep=sleep,
                readiness=readiness,
                mood=mood,
                date=datetime.now(timezone.utc),
                answers=f"energy={energy},sleep={sleep},readiness={readiness},mood={mood}"
            )
            
            print(f"📝 Survey object created")
            
            session.add(survey)
            
            user.energy = energy
            user.sleep_quality = sleep 
            user.readiness = readiness
            user.mood = mood
            user.last_survey_at = datetime.now(timezone.utc)
            user.last_survey_type = survey_type
            
            print(f"📝 User fields updated")
            
            session.commit()
            print(f"✅ Survey saved successfully with ID: {survey.id}")
            
            session.close()
            return True
            
        except Exception as e:
            print(f"❌ Error in record_survey: {e}")
            traceback.print_exc()
            if 'session' in locals():
                try:
                    session.rollback()
                    session.close()
                except:
                    pass
        return False
        

    @staticmethod
    def get_today_surveys(user_id: int) -> List[Dict]:
        """Получить опросы пользователя за сегодня"""
        try:
            session = get_session()
            today = datetime.now(timezone.utc).date()
            

            surveys = session.query(Survey).filter(
                Survey.user_id == user_id,
                func.date(Survey.date) == today  
            ).order_by(Survey.date.desc()).all()  
            
            result = []
            for survey in surveys:
                result.append({
                    "type": survey.survey_type,
                    "time": survey.date, 
                    "energy": survey.energy,
                    "sleep": survey.sleep,
                    "readiness": survey.readiness,
                    "mood": survey.mood
                })
            
            session.close()
            return result
            
        except Exception as e:
            print(f"❌ Ошибка получения опросов: {e}")
            return []
        
    @staticmethod
    def has_completed_survey_today(user_id: int, survey_type: str) -> bool:
        """Проверить, проходил ли пользователь опрос определенного типа сегодня"""
        try:
            session = get_session()
            today = datetime.now(timezone.utc).date()
            
            count = session.query(Survey).filter(
                Survey.user_id == user_id,
                Survey.survey_type == survey_type,
                func.date(Survey.date) == today  # ← ИСПРАВЛЕНО
            ).count()
            
            session.close()
            return count > 0
            
        except Exception as e:
            print(f"❌ Ошибка проверки опроса: {e}")
            return False
    
    @staticmethod
    def add_points(user_id: int, points: int, reason: str = "") -> bool:
        """Добавить очки пользователю"""
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return False
            
            user.points += points
            
            new_level = min((user.points // 100) + 1, 5)
            if new_level > user.level:
                user.level = new_level
            
            session.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка при добавлении очков: {e}")
            return False
        finally:
            session.close()


class FootballMetrics(MetricsCollector):
    """Метрики специфические для футбола"""
    
    @staticmethod
    def get_team_performance(org_id: int) -> Dict:
        """Производительность команды"""
        session = get_session()
        try:
            stats = MetricsCollector.get_organization_stats(org_id)
            users = session.query(User).filter(User.org_id == org_id).all()
            
            positions = {}
            for user in users:
                pos = user.position or "Участник"
                if pos not in positions:
                    positions[pos] = {
                        "count": 0,
                        "avg_points": 0,
                        "avg_level": 0,
                        "total_points": 0,
                        "total_level": 0
                    }
                positions[pos]["count"] += 1
                positions[pos]["total_points"] += user.points
                positions[pos]["total_level"] += user.level
            
            for pos in positions:
                positions[pos]["avg_points"] = round(positions[pos]["total_points"] / positions[pos]["count"], 1)
                positions[pos]["avg_level"] = round(positions[pos]["total_level"] / positions[pos]["count"], 1)
            
            return {
                "org_stats": stats,
                "positions_breakdown": positions,
                "team_cohesion": round(sum([p["avg_level"] for p in positions.values()]) / len(positions), 1) if positions else 0
            }
        finally:
            session.close()


def get_nsk_time():
    """Получить текущее время в Новосибирске"""
    nsk_tz = pytz.timezone('Asia/Novosibirsk')
    return datetime.now(nsk_tz)

def get_nsk_today_start():
    """Получить начало текущего дня в Новосибирске"""
    nsk_tz = pytz.timezone('Asia/Novosibirsk')
    now_nsk = datetime.now(nsk_tz)
    return now_nsk.replace(hour=0, minute=0, second=0, microsecond=0)

def convert_to_utc_for_db(nsk_datetime):
    """Конвертировать время Новосибирска в UTC для запросов к БД"""
    if nsk_datetime.tzinfo is None:
        nsk_tz = pytz.timezone('Asia/Novosibirsk')
        nsk_datetime = nsk_tz.localize(nsk_datetime)
    return nsk_datetime.astimezone(timezone.utc)