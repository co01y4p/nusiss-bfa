import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.models import UserModel
from app.security.authentication import hash_password


def main() -> None:
    email = input("Manager email: ").strip().lower()
    password = getpass.getpass("Manager password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not email or "@" not in email:
        raise SystemExit("A valid email is required")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    with SessionLocal() as db:
        existing = db.scalar(select(UserModel).where(UserModel.email == email))
        if existing is not None:
            raise SystemExit("A user with that email already exists")
        db.add(UserModel(email=email, password_hash=hash_password(password), role="MANAGER"))
        db.commit()
    print("Manager account created")


if __name__ == "__main__":
    main()
