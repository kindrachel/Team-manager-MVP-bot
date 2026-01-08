import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import traceback

from io import BytesIO
from services.report_formatter import ReportFormatter
from services.ai_service import AIService
from services.metrics_analyzer import ProffKonstaltingMetrics
from database import get_session, User, Organization, Challenge, Survey, MetricsSurvey

logger = logging.getLogger(__name__)

class AIReportAnalyzer:
    """AI-анализатор для генерации умных отчетов"""
    
    def __init__(self):
        self.ai_service = AIService()
        logger.info("AIReportAnalyzer инициализирован")
    
    async def generate_daily_report_pdf(self, org_id: int) -> BytesIO:
        """Генерация PDF отчета за день"""
        report_data = await self.generate_daily_report(org_id)
        if "error" in report_data:
            return ReportFormatter.create_text_report({"error": report_data["error"]})
        
        return ReportFormatter.create_daily_report_pdf(report_data)

    async def generate_members_report_pdf(self, org_id: int) -> BytesIO:
        """Генерация PDF отчета по игрокам"""
        report_data = await self.generate_detailed_member_report(org_id)
        if "error" in report_data:
            return ReportFormatter.create_text_report({"error": report_data["error"]})
        
        return ReportFormatter.create_members_report_pdf(report_data)

    async def generate_daily_report(self, org_id: int) -> Dict:
        """
        Генерация ежедневного отчета для администратора
        """
        session = get_session()
        try:
            org = session.query(Organization).filter(Organization.id == org_id).first()
            users = session.query(User).filter(User.org_id == org_id).all()
            
            if not users:
                return {"error": "В команде нет пользователей"}
            
            # Собираем данные за сегодня
            today = datetime.now().date()
            daily_stats = {
                "total_members": len(users),
                "active_today": 0,
                "completed_challenges_today": 0,
                "submitted_surveys_today": 0,
                "total_points_earned": 0
            }
            
            user_details = []
            
            for user in users:
                try:
                    # Получаем все челленджи пользователя
                    all_challenges = session.query(Challenge).filter(
                        Challenge.user_id == user.user_id
                    ).all()

                    # Фильтруем челленджи, выполненные сегодня
                    challenges_today = []
                    for challenge in all_challenges:
                        if (hasattr(challenge, 'status') and
                            challenge.status == "COMPLETED" and
                            hasattr(challenge, 'completed_at') and
                            challenge.completed_at and
                            challenge.completed_at.date() == today):
                            challenges_today.append(challenge)

                    # Получаем опросы пользователя за сегодня с правильной фильтрацией по времени
                    from sqlalchemy import func
                    surveys_today = session.query(Survey).filter(
                        Survey.user_id == user.id,
                        func.date(Survey.date) == today
                    ).all()

                    # Подсчитываем очки, заработанные сегодня
                    points_today = sum(getattr(c, 'points', 0) for c in challenges_today)

                except Exception as e:
                    logger.warning(f"Ошибка получения данных для пользователя {user.id}: {e}")
                    challenges_today = []
                    surveys_today = []
                    points_today = 0

                # Пользователь активен, если выполнил челленджи или прошел опросы сегодня
                is_active = len(challenges_today) > 0 or len(surveys_today) > 0

                if is_active:
                    daily_stats["active_today"] += 1
                    daily_stats["completed_challenges_today"] += len(challenges_today)
                    daily_stats["submitted_surveys_today"] += len(surveys_today)
                    daily_stats["total_points_earned"] += points_today

                user_detail = {
                    "name": getattr(user, 'name', 'Неизвестно'),
                    "points": getattr(user, 'points', 0),
                    "level": getattr(user, 'level', 1),
                    "active_today": is_active,
                    "challenges_today": len(challenges_today),
                    "surveys_today": len(surveys_today),
                    "points_today": points_today,
                }
                
                if hasattr(user, 'energy'):
                    user_detail["energy"] = user.energy
                if hasattr(user, 'readiness'):
                    user_detail["readiness"] = user.readiness
                
                user_details.append(user_detail)
            
            user_details.sort(key=lambda x: (x["active_today"], x["points_today"]), reverse=True)
            
            avg_energy = 0
            avg_readiness = 0
            energy_count = 0
            readiness_count = 0
            
            for user in user_details:
                if "energy" in user and user["energy"] is not None:
                    avg_energy += user["energy"]
                    energy_count += 1
                if "readiness" in user and user["readiness"] is not None:
                    avg_readiness += user["readiness"]
                    readiness_count += 1
            
            if energy_count > 0:
                avg_energy = avg_energy / energy_count
            if readiness_count > 0:
                avg_readiness = avg_readiness / readiness_count
            
            report_data = {
                "org_name": getattr(org, 'name', 'Неизвестная команда'),
                "date": today.strftime("%d.%m.%Y"),
                "daily_stats": daily_stats,
                "top_performers": user_details[:3],
                "needs_attention": [u for u in user_details if not u["active_today"]],
                "team_overview": {
                    "avg_energy": avg_energy,
                    "avg_readiness": avg_readiness
                }
            }
            
            logger.info(f"Данные для отчета собраны: {daily_stats}")
            
            # Генерируем AI-анализ
            prompt = f"""
            Ты спортивный аналитик команды. Проанализируй ежедневный отчет.
            
            ДАННЫЕ КОМАНДЫ "{report_data['org_name']}" за {report_data['date']}:
            Всего участников: {report_data['daily_stats']['total_members']}
            Активных сегодня: {report_data['daily_stats']['active_today']}
            Выполнено челленджей: {report_data['daily_stats']['completed_challenges_today']}
            Пройдено опросов: {report_data['daily_stats']['submitted_surveys_today']}
            Заработано очков: {report_data['daily_stats']['total_points_earned']}
            
            Средняя энергия команды: {report_data['team_overview']['avg_energy']:.1f}
            Средняя готовность: {report_data['team_overview']['avg_readiness']:.1f}
            
            ЛУЧШИЕ ИГРОКИ СЕГОДНЯ:
            {report_data['top_performers']}
            
            ТРЕБУЮТ ВНИМАНИЯ (не активны сегодня):
            {report_data['needs_attention']}
            
            СОЗДАЙ АНАЛИТИЧЕСКИЙ ОТЧЕТ ВКЛЮЧАЮЩИЙ:
            1. Краткое резюме дня (2-3 предложения)
            2. Общее настроение команды (positive/neutral/negative)
            3. Ключевые достижения дня
            4. Проблемные зоны (если есть)
            5. 3 конкретные рекомендации на завтра
            6. На чем сосредоточиться в тренировках
            
            Формат ответа ТОЛЬКО JSON:
            {{
                "executive_summary": "Краткое резюме",
                "team_mood": "positive/neutral/negative",
                "key_achievements": ["достижение 1", "достижение 2"],
                "problem_areas": ["проблема 1", "проблема 2"],
                "ai_recommendations": [
                    {{"action": "действие", "priority": "high/medium/low", "reason": "почему важно"}}
                ],
                "tomorrow_focus": "Главный фокус на завтра",
                "motivational_message": "Сообщение для команды"
            }}
            
            ВАЖНО: Ответ должен быть ТОЛЬКО JSON, без дополнительного текста.
            """
            
            try:
                # Используем get_json_response вместо answer_user_question
                analysis = await self.ai_service.get_json_response(prompt)
                
                if "error" in analysis:
                    logger.error(f"Ошибка AI-анализа: {analysis['error']}")
                    # Fallback анализ
                    analysis = self._get_fallback_analysis(report_data)
                
                logger.info("AI-анализ успешно сгенерирован")
            except Exception as e:
                logger.error(f"Ошибка парсинга AI-ответа: {e}")
                logger.error(traceback.format_exc())
                analysis = self._get_fallback_analysis(report_data)
            
            # Объединяем данные
            full_report = {
                **report_data,
                "ai_analysis": analysis,
                "generated_at": datetime.now().isoformat()
            }
            
            return full_report
            
        except Exception as e:
            logger.error(f"Ошибка генерации отчета: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            session.close()
    
    def _get_fallback_analysis(self, report_data: Dict) -> Dict:
        """Fallback анализ если AI недоступен"""
        return {
            "executive_summary": f"Команда {report_data['org_name']} показала активность {report_data['daily_stats']['active_today']}/{report_data['daily_stats']['total_members']} игроков",
            "team_mood": "neutral",
            "key_achievements": ["Ежедневная активность", "Участие в челленджах"],
            "problem_areas": ["Не все участники активны"],
            "ai_recommendations": [
                {"action": "Мотивировать неактивных участников", "priority": "medium", "reason": "Повышение вовлеченности"}
            ],
            "tomorrow_focus": "Повышение активности всех участников",
            "motivational_message": "Команда, продолжайте работать над собой!"
        }
    
    async def generate_detailed_member_report(self, org_id: int) -> Dict:
        """
        Детальный отчет по каждому участнику с AI-анализом
        """
        session = get_session()
        try:
            users = session.query(User).filter(User.org_id == org_id).all()
            
            if not users:
                return {"error": "В команде нет пользователей"}
            
            member_reports = []
            
            for user in users:
                # Собираем статистику пользователя
                try:
                    challenges = session.query(Challenge).filter(
                        Challenge.user_id == user.user_id
                    ).all()

                    surveys = session.query(Survey).filter(
                        Survey.user_id == user.id
                    ).all()
                    
                    # Берем последние 5 опросов
                    recent_surveys = surveys[-5:] if len(surveys) > 5 else surveys
                    
                    completed_challenges = [c for c in challenges if hasattr(c, 'status') and c.status == "COMPLETED"]
                    
                    # Безопасно получаем энергию из опросов
                    total_energy = 0
                    energy_count = 0
                    for survey in recent_surveys:
                        if hasattr(survey, 'energy') and survey.energy is not None:
                            total_energy += survey.energy
                            energy_count += 1
                    
                    avg_energy = total_energy / energy_count if energy_count > 0 else 0
                    
                except Exception as e:
                    logger.warning(f"Ошибка сбора данных для {user.name}: {e}")
                    challenges = []
                    completed_challenges = []
                    avg_energy = 0
                    recent_surveys = []
                
                # Получаем последние результаты метрик-опроса
                metrics_survey = session.query(MetricsSurvey).filter(
                    MetricsSurvey.user_id == user.id
                ).order_by(MetricsSurvey.created_at.desc()).first()

                metrics_data = {}
                if metrics_survey and metrics_survey.results:
                    metrics_data = metrics_survey.results

                user_data = {
                    "name": getattr(user, 'name', 'Неизвестно'),
                    "points": getattr(user, 'points', 0),
                    "level": getattr(user, 'level', 1),
                    "total_challenges": len(challenges),
                    "completed_challenges": len(completed_challenges),
                    "completion_rate": (len(completed_challenges) / len(challenges) * 100) if challenges else 0,
                    "recent_surveys": len(recent_surveys),
                    "avg_energy": avg_energy,
                    "metrics_results": metrics_data
                }
                
                # Формируем данные метрик для анализа
                metrics_info = ""
                if user_data['metrics_results']:
                    metrics_info = "\nРЕЗУЛЬТАТЫ МЕТРИК ПРОФЕССИОНАЛЬНОГО РАЗВИТИЯ:\n"
                    for metric_key, metric_result in user_data['metrics_results'].items():
                        if isinstance(metric_result, dict):
                            score = metric_result.get('score', 0)
                            interpretation = metric_result.get('interpretation', 'Нет данных')
                            metrics_info += f"- {metric_result.get('name', metric_key)}: {score} - {interpretation}\n"
                        else:
                            metrics_info += f"- {metric_key}: {metric_result}\n"

                prompt = f"""
                Ты персональный тренер. Проанализируй данные игрока и результаты метрик профессионального развития.

                ДАННЫЕ ИГРОКА {user_data['name']}:
                - Уровень: {user_data['level']}
                - Очки: {user_data['points']}
                - Всего челленджей: {user_data['total_challenges']}
                - Выполнено: {user_data['completed_challenges']}
                - Процент выполнения: {user_data['completion_rate']:.1f}%
                - Средняя энергия: {user_data['avg_energy']:.1f}{metrics_info}

                ДАЙ АНАЛИЗ ВКЛЮЧАЮЩИЙ:
                1. Краткую характеристику игрока с учетом метрик
                2. Сильные стороны на основе метрик (2-3 пункта)
                3. Области для улучшения на основе метрик (2-3 пункта)
                4. Персональные рекомендации на основе метрик (3-4 пункта)
                5. Рекомендации по развитию конкретных метрик

                Формат ответа JSON:
                {{
                    "player_summary": "Краткая характеристика с учетом метрик",
                    "strengths": ["сильная сторона 1", "сильная сторона 2", "сильная сторона 3"],
                    "improvement_areas": ["область улучшения 1", "область улучшения 2", "область улучшения 3"],
                    "personal_recommendations": ["рекомендация 1", "рекомендация 2", "рекомендация 3", "рекомендация 4"],
                    "metrics_based_recommendations": ["рекомендация по метрике 1", "рекомендация по метрике 2"],
                    "motivational_note": "Мотивационное сообщение для игрока"
                }}
                """
                
                # Fallback анализ по умолчанию
                user_analysis = {
                    "player_summary": f"Игрок {user_data['name']}, уровень {user_data['level']}",
                    "strengths": ["Мотивация", "Регулярность"],
                    "improvement_areas": ["Нужны дополнительные данные"],
                    "personal_recommendations": ["Участвовать в ежедневных челленджах", "Регулярно проходить опросы", "Ставить личные цели"],
                    "metrics_based_recommendations": ["Пройти метрики-опрос для персонализированных рекомендаций"],
                    "motivational_note": "Продолжай работать над собой!"
                }
                
                try:
                    # Используем get_json_response вместо answer_user_question
                    ai_response = await self.ai_service.get_json_response(prompt)
                    if isinstance(ai_response, dict) and "error" not in ai_response:
                        user_analysis = ai_response
                except Exception as e:
                    logger.error(f"Ошибка AI-анализа для {user.name}: {e}")
                    # Оставляем fallback анализ
                
                member_reports.append({
                    "user_data": user_data,
                    "ai_analysis": user_analysis
                })
            
            # Fallback для общего анализа команды
            team_analysis = {
                "team_assessment": f"Команда из {len(users)} игроков показывает стабильный прогресс",
                "training_recommendations": ["Регулярные тренировки", "Индивидуальный подход к каждому игроку"],
                "motivation_strategies": ["Поощрение активности", "Командные цели и соревнования"],
                "coach_notes": f"Продолжайте мониторить прогресс {len(users)} игроков и адаптировать тренировки под их нужды"
            }
            
            try:
                # Генерируем общий анализ команды
                team_prompt = f"""
                Ты главный тренер. Проанализируй команду на основе данных игроков.
                
                ОБЩАЯ СТАТИСТИКА:
                - Всего игроков: {len(users)}
                - Средний уровень: {sum(getattr(u, 'level', 1) for u in users) / len(users):.1f}
                - Средние очки: {sum(getattr(u, 'points', 0) for u in users) / len(users):.1f}
                - Общее количество выполненных челленджей: {sum(len([c for c in session.query(Challenge).filter(Challenge.user_id == u.id).all() if hasattr(c, 'status') and c.status == "COMPLETED"]) for u in users)}
                
                ДАЙ ОБЩИЕ РЕКОМЕНДАЦИИ ДЛЯ КОМАНДЫ:
                1. Общая оценка состояния команды
                2. Рекомендации по тренировочному процессу
                3. Советы по мотивации игроков
                
                Формат ответа JSON:
                {{
                    "team_assessment": "Общая оценка команды",
                    "training_recommendations": ["рекомендация 1", "рекомендация 2"],
                    "motivation_strategies": ["стратегия 1", "стратегия 2"],
                    "coach_notes": "Заметки для тренера"
                }}
                """
                
                ai_response = await self.ai_service.get_json_response(team_prompt)
                if isinstance(ai_response, dict) and "error" not in ai_response:
                    team_analysis.update(ai_response)  # Обновляем fallback значения
            except Exception as e:
                logger.error(f"Ошибка AI-анализа команды: {e}")
                # Используем fallback team_analysis
            
            return {
                "member_reports": member_reports,
                "team_analysis": team_analysis,  # Теперь переменная всегда определена
                "total_members": len(users),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Ошибка детального отчета: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            session.close()

    async def generate_survey_analysis_report(self, org_id: int) -> Dict:
        """
        Генерация отчета с анализом опросов и AI рекомендациями по росту и расслаблению
        """
        session = get_session()
        try:
            # Собираем все оценки из опросов организации
            survey_data = self._collect_survey_ratings(org_id, session)

            if not survey_data['surveys'] and not survey_data['metrics_surveys']:
                return {"error": "Недостаточно данных опросов для анализа"}

            # Анализируем тренды оценок
            trends_analysis = self._analyze_rating_trends(survey_data)

            # Анализируем метрики профессионального развития
            metrics_analysis = self._analyze_metrics_ratings(survey_data)

            # Генерируем AI рекомендации
            ai_recommendations = await self._generate_growth_relaxation_recommendations(
                trends_analysis, metrics_analysis, survey_data
            )

            # Формируем полный отчет
            report = {
                "organization_id": org_id,
                "analysis_period": survey_data['period'],
                "survey_statistics": {
                    "total_surveys": len(survey_data['surveys']),
                    "total_metrics_surveys": len(survey_data['metrics_surveys']),
                    "unique_users": len(survey_data['users_data'])
                },
                "trends_analysis": trends_analysis,
                "metrics_analysis": metrics_analysis,
                "ai_recommendations": ai_recommendations,
                "generated_at": datetime.now().isoformat()
            }

            return report

        except Exception as e:
            logger.error(f"Ошибка генерации отчета анализа опросов: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            session.close()

    def _collect_survey_ratings(self, org_id: int, session) -> Dict:
        """Сбор всех оценок из опросов организации"""
        from database import Survey, MetricsSurvey, User

        # Получаем всех пользователей организации
        users = session.query(User).filter(User.org_id == org_id).all()
        user_ids = [u.id for u in users]  # Используем id для Survey
        user_ids_bigint = [u.user_id for u in users]  # Используем user_id для MetricsSurvey

        # Собираем обычные опросы (Survey)
        surveys = session.query(Survey).filter(
            Survey.user_id.in_(user_ids)
        ).order_by(Survey.date.desc()).all()

        # Собираем метрики-опросы (MetricsSurvey)
        metrics_surveys = session.query(MetricsSurvey).filter(
            MetricsSurvey.user_id.in_(user_ids_bigint)
        ).order_by(MetricsSurvey.created_at.desc()).all()

        # Определяем период анализа
        all_dates = []
        for survey in surveys:
            if survey.date:
                all_dates.append(survey.date)
        for m_survey in metrics_surveys:
            if m_survey.created_at:
                all_dates.append(m_survey.created_at)

        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            period = f"{min_date.strftime('%d.%m.%Y')} - {max_date.strftime('%d.%m.%Y')}"
        else:
            period = "Нет данных"

        # Группируем данные по пользователям
        users_data = {}
        for user in users:
            users_data[user.id] = {
                'user_id': user.user_id,
                'name': user.name or 'Неизвестно',
                'surveys': [],
                'metrics_surveys': []
            }

        # Добавляем обычные опросы
        for survey in surveys:
            if survey.user_id in users_data:
                survey_data = {
                    'date': survey.date.isoformat() if survey.date else None,
                    'energy': survey.energy,
                    'sleep': survey.sleep,
                    'readiness': survey.readiness,
                    'mood': survey.mood
                }
                users_data[survey.user_id]['surveys'].append(survey_data)

        # Добавляем метрики-опросы
        for m_survey in metrics_surveys:
            # Находим соответствующего пользователя
            user_record = next((u for u in users if u.user_id == m_survey.user_id), None)
            if user_record and user_record.id in users_data:
                metrics_data = {
                    'date': m_survey.created_at.isoformat() if m_survey.created_at else None,
                    'overall_score': m_survey.overall_score,
                    'category': m_survey.category,
                    'results': m_survey.results or {}
                }
                users_data[user_record.id]['metrics_surveys'].append(metrics_data)

        return {
            'surveys': surveys,
            'metrics_surveys': metrics_surveys,
            'users_data': users_data,
            'period': period
        }

    def _analyze_rating_trends(self, survey_data: Dict) -> Dict:
        """Анализ трендов оценок energy, sleep, readiness, mood"""
        trends = {
            'energy': {'avg': 0, 'trend': 'stable', 'count': 0},
            'sleep': {'avg': 0, 'trend': 'stable', 'count': 0},
            'readiness': {'avg': 0, 'trend': 'stable', 'count': 0},
            'mood_distribution': {}
        }

        all_energy = []
        all_sleep = []
        all_readiness = []
        all_moods = []

        # Собираем все оценки
        for user_data in survey_data['users_data'].values():
            for survey in user_data['surveys']:
                if survey['energy'] is not None:
                    all_energy.append(survey['energy'])
                if survey['sleep'] is not None:
                    all_sleep.append(survey['sleep'])
                if survey['readiness'] is not None:
                    all_readiness.append(survey['readiness'])
                if survey['mood']:
                    all_moods.append(survey['mood'])

        # Рассчитываем средние
        if all_energy:
            trends['energy']['avg'] = round(sum(all_energy) / len(all_energy), 1)
            trends['energy']['count'] = len(all_energy)

        if all_sleep:
            trends['sleep']['avg'] = round(sum(all_sleep) / len(all_sleep), 1)
            trends['sleep']['count'] = len(all_sleep)

        if all_readiness:
            trends['readiness']['avg'] = round(sum(all_readiness) / len(all_readiness), 1)
            trends['readiness']['count'] = len(all_readiness)

        # Анализируем распределение настроений
        mood_counts = {}
        for mood in all_moods:
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
        trends['mood_distribution'] = mood_counts

        # Определяем тренды (упрощенная версия - можно улучшить с анализом по времени)
        if trends['energy']['avg'] < 3:
            trends['energy']['trend'] = 'low'
        elif trends['energy']['avg'] > 4:
            trends['energy']['trend'] = 'high'

        if trends['sleep']['avg'] < 3:
            trends['sleep']['trend'] = 'low'
        elif trends['sleep']['avg'] > 4:
            trends['sleep']['trend'] = 'high'

        if trends['readiness']['avg'] < 3:
            trends['readiness']['trend'] = 'low'
        elif trends['readiness']['avg'] > 4:
            trends['readiness']['trend'] = 'high'

        return trends

    def _analyze_metrics_ratings(self, survey_data: Dict) -> Dict:
        """Анализ оценок по метрикам профессионального развития"""
        metrics_stats = {}

        # Собираем все оценки по метрикам
        for user_data in survey_data['users_data'].values():
            for m_survey in user_data['metrics_surveys']:
                results = m_survey.get('results', {})
                if isinstance(results, dict):
                    for metric_key, metric_data in results.items():
                        if metric_key not in metrics_stats:
                            metrics_stats[metric_key] = {
                                'name': metric_data.get('name', metric_key) if isinstance(metric_data, dict) else metric_key,
                                'scores': [],
                                'avg_score': 0,
                                'count': 0
                            }

                        if isinstance(metric_data, dict) and 'score' in metric_data:
                            score = metric_data['score']
                            if isinstance(score, (int, float)):
                                metrics_stats[metric_key]['scores'].append(score)

        # Рассчитываем средние
        for metric_key, stats in metrics_stats.items():
            if stats['scores']:
                stats['avg_score'] = round(sum(stats['scores']) / len(stats['scores']), 1)
                stats['count'] = len(stats['scores'])

        # Определяем сильные и слабые метрики
        strong_metrics = []
        weak_metrics = []

        for metric_key, stats in metrics_stats.items():
            if stats['avg_score'] >= 4:
                strong_metrics.append({
                    'metric': stats['name'],
                    'avg_score': stats['avg_score'],
                    'recommendation': 'relax'  # Можно расслабиться, уже хорошо развито
                })
            elif stats['avg_score'] <= 2:
                weak_metrics.append({
                    'metric': stats['name'],
                    'avg_score': stats['avg_score'],
                    'recommendation': 'grow'  # Нужно развивать
                })

        return {
            'metrics_stats': metrics_stats,
            'strong_metrics': strong_metrics,
            'weak_metrics': weak_metrics,
            'total_metrics_surveys': len([s for u in survey_data['users_data'].values() for s in u['metrics_surveys']])
        }

    async def _generate_growth_relaxation_recommendations(self, trends_analysis: Dict,
                                                         metrics_analysis: Dict,
                                                         survey_data: Dict) -> Dict:
        """Генерация AI рекомендаций по областям роста и расслабления"""

        # Формируем контекст для AI
        context = f"""
        АНАЛИЗ ОПРОСОВ КОМАНДЫ:

        ТРЕНДЫ ПОКАЗАТЕЛЕЙ:
        - Энергия: средняя {trends_analysis['energy']['avg']}/5 ({trends_analysis['energy']['count']} оценок)
        - Сон: средний {trends_analysis['sleep']['avg']}/5 ({trends_analysis['sleep']['count']} оценок)
        - Готовность: средняя {trends_analysis['readiness']['avg']}/5 ({trends_analysis['readiness']['count']} оценок)
        - Распределение настроений: {trends_analysis['mood_distribution']}

        МЕТРИКИ ПРОФЕССИОНАЛЬНОГО РАЗВИТИЯ:
        """

        for metric_key, stats in metrics_analysis['metrics_stats'].items():
            context += f"- {stats['name']}: средняя {stats['avg_score']}/5 ({stats['count']} оценок)\n"

        context += f"""

        СИЛЬНЫЕ МЕТРИКИ (можно расслабиться):
        """
        for metric in metrics_analysis['strong_metrics']:
            context += f"- {metric['metric']}: {metric['avg_score']}/5\n"

        context += f"""

        СЛАБЫЕ МЕТРИКИ (нужно развивать):
        """
        for metric in metrics_analysis['weak_metrics']:
            context += f"- {metric['metric']}: {metric['avg_score']}/5\n"

        prompt = f"""
        Ты HR-аналитик и спортивный психолог. На основе анализа опросов команды создай рекомендации по развитию и расслаблению.

        {context}

        СОЗДАЙ РЕКОМЕНДАЦИИ В ФОРМАТЕ JSON:

        {{
            "executive_summary": "Краткое резюме состояния команды (2-3 предложения)",
            "growth_areas": [
                {{
                    "area": "Область для развития",
                    "priority": "high/medium/low",
                    "reason": "Почему важно развивать",
                    "specific_actions": ["Конкретное действие 1", "Конкретное действие 2"]
                }}
            ],
            "relaxation_areas": [
                {{
                    "area": "Область где можно расслабиться",
                    "reason": "Почему можно не беспокоиться",
                    "maintenance_actions": ["Действие для поддержания уровня"]
                }}
            ],
            "team_mood_analysis": "Анализ общего настроения команды",
            "immediate_actions": ["Срочные действия на этой неделе"],
            "long_term_strategy": "Стратегия развития на 1-3 месяца",
            "motivational_message": "Мотивационное сообщение для команды"
        }}

        ВАЖНО:
        - Growth areas: фокусируйся на низких показателях энергии, сна, готовности и слабых метриках
        - Relaxation areas: отмечай высокие показатели и сильные метрики
        - Будь конкретен и практичен
        - Учитывай специфику спортивной команды
        """

        try:
            ai_response = await self.ai_service.get_json_response(prompt)
            if isinstance(ai_response, dict) and "error" not in ai_response:
                return ai_response
            else:
                # Fallback рекомендации
                return self._get_fallback_recommendations(trends_analysis, metrics_analysis)
        except Exception as e:
            logger.error(f"Ошибка генерации AI рекомендаций: {e}")
            return self._get_fallback_recommendations(trends_analysis, metrics_analysis)

    def _get_fallback_recommendations(self, trends_analysis: Dict, metrics_analysis: Dict) -> Dict:
        """Fallback рекомендации если AI недоступен"""
        growth_areas = []
        relaxation_areas = []

        # Анализ трендов
        if trends_analysis['energy']['avg'] < 3:
            growth_areas.append({
                "area": "Уровень энергии",
                "priority": "high",
                "reason": "Низкая энергия влияет на производительность и мотивацию",
                "specific_actions": ["Увеличить время отдыха", "Ввести регулярные перерывы", "Проверить питание"]
            })

        if trends_analysis['sleep']['avg'] < 3:
            growth_areas.append({
                "area": "Качество сна",
                "priority": "high",
                "reason": "Недосып снижает готовность и концентрацию",
                "specific_actions": ["Нормализовать режим сна", "Избегать поздних тренировок", "Ввести ритуалы перед сном"]
            })

        if trends_analysis['readiness']['avg'] >= 4:
            relaxation_areas.append({
                "area": "Готовность к тренировкам",
                "reason": "Команда показывает высокую готовность",
                "maintenance_actions": ["Поддерживать текущий режим", "Мониторить изменения"]
            })

        # Анализ метрик
        for metric in metrics_analysis['weak_metrics']:
            growth_areas.append({
                "area": f"Метрика: {metric['metric']}",
                "priority": "medium",
                "reason": f"Низкий балл {metric['avg_score']}/5 требует развития",
                "specific_actions": [f"Пройти тренинг по {metric['metric']}", "Регулярно оценивать прогресс"]
            })

        for metric in metrics_analysis['strong_metrics']:
            relaxation_areas.append({
                "area": f"Метрика: {metric['metric']}",
                "reason": f"Высокий балл {metric['avg_score']}/5 - сильная сторона",
                "maintenance_actions": [f"Поддерживать уровень в {metric['metric']}"]
            })

        return {
            "executive_summary": f"Команда показывает средние результаты. Энергия: {trends_analysis['energy']['avg']}/5, Сон: {trends_analysis['sleep']['avg']}/5, Готовность: {trends_analysis['readiness']['avg']}/5",
            "growth_areas": growth_areas,
            "relaxation_areas": relaxation_areas,
            "team_mood_analysis": "Команда стабильна, требует внимания к восстановлению",
            "immediate_actions": ["Провести опрос по самочувствию", "Организовать встречу с тренером"],
            "long_term_strategy": "Разработать программу развития слабых метрик и поддержания сильных сторон",
            "motivational_message": "Команда, вы делаете отличную работу! Давайте вместе поработаем над областями роста и сохраним наши сильные стороны."
        }

