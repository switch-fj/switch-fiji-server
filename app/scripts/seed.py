from sqlalchemy import select

from app.core.auth import Authentication
from app.core.config import Config
from app.database.postgres import AsyncSessionMaker
from app.modules.users.model import User
from app.shared.schema import UserRoleEnum


async def seed_admin():
    async with AsyncSessionMaker() as session:
        admin_email = Config.DEFAULT_ADMIN_EMAIL
        default_pass = Config.DEFAULT_ADMIN_PASS

        result = await session.exec(select(User).where(User.email == admin_email))
        admin = result.scalar_one_or_none()

        if not admin:
            new_admin = User(
                email=admin_email,
                password=Authentication.generate_password_hash(default_pass),
                is_email_verified=True,
                role=UserRoleEnum.ADMIN.value,
            )
            session.add(new_admin)
            await session.commit()
            print("[seed] Default admin created.")
        else:
            print("[seed] Admin already exists.")
