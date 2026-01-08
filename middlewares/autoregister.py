import logging
from config import load_config

logger = logging.getLogger(__name__)

async def ensure_super_admin_exists():
    """Убедиться, что суперадмин существует в БД"""
    config = load_config()
    
    if not config.admin_ids:
        logger.warning("⚠️ В .env не указаны ADMIN_IDS. Суперадмины не будут созданы.")
        return
    
    from database import get_session, User, Organization, UserRole
    
    session = get_session()
    try:
        for admin_id in config.admin_ids:
            user = session.query(User).filter(User.user_id == admin_id).first()
            if not user:
                logger.info(f"👑 Создаю суперадмина с ID: {admin_id}")
                
                org = Organization(
                    name="Супер-администраторы",
                    org_type="admin",
                    admin_id=admin_id
                )
                session.add(org)
                session.flush() 
                
                user = User(
                    user_id=admin_id,
                    chat_id=admin_id,
                    org_id=org.id,
                    name=f"Супер-админ {admin_id}",
                    phone="+70000000000",
                    role=UserRole.SUPER_ADMIN.value,
                    points=0,
                    level=99
                )
                session.add(user)
                logger.info(f"✅ Суперадмин {admin_id} создан")
        
        session.commit()
        logger.info(f"✅ Все суперадмины проверены/созданы: {config.admin_ids}")
    except Exception as e:
        logger.error(f"❌ Ошибка создания суперадмина: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()