from flask import current_app

from database.db import User, db
from database.schemas import ChangePasswordSchema, ProfileUpdateSchema


def update_profile(user: User, data: ProfileUpdateSchema) -> None:
    user.display_name = data.display_name
    user.default_currency = data.default_currency
    db.session.commit()
    current_app.logger.info("Profile updated for user_id=%s", user.id)


def change_password(user: User, data: ChangePasswordSchema) -> bool:
    if not user.check_password(data.current_password):
        return False

    user.set_password(data.new_password)
    db.session.commit()
    current_app.logger.info("Password changed for user_id=%s", user.id)
    return True
