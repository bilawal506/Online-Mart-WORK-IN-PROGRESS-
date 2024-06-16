from datetime import timedelta
from typing import Annotated
from sqlmodel import Session, SQLModel, select
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from .models import User, engine, get_session
from .auth import *
from .settings import settings

app = FastAPI()

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS
)

templates = Jinja2Templates(directory="templates")

class EmailSchema(BaseModel):
    email: EmailStr

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

create_db_and_tables()

@app.get("/users/", response_model=list[User])
def read_users(session: Annotated[Session, Depends(get_session)], current_user: User = Depends(get_current_admin_user)):
    users = session.exec(select(User)).all()
    return users

@app.post("/signup/", response_model=User)
def create_user(user: User, session: Annotated[Session, Depends(get_session)]):
    existing_user = session.exec(select(User).where(User.username == user.username)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    existing_email = session.exec(select(User).where(User.email == user.email)).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")

    existing_phone_number = session.exec(select(User).where(User.phone_number == user.phone_number)).first()
    if existing_phone_number:
        raise HTTPException(status_code=400, detail="Phone number already exists")
    existing_id = session.exec(select(User).where(User.id == user.id)).first()
    if existing_id:
        raise HTTPException(status_code=400, detail="ID already exists")

    user.password = get_password_hash(user.password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@app.post("/token", response_model=Token)
async def login_for_access_token(session: Annotated[Session, Depends(get_session)], form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.post("/forgot-password/")
async def forgot_password(background_tasks: BackgroundTasks, email: EmailSchema, session: Annotated[Session, Depends(get_session)]):
    user = session.exec(select(User).where(User.email == email.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    reset_token = create_reset_token(email.email)
    reset_url = f"http://localhost:8001/reset-password?token={reset_token}"

    message = MessageSchema(
        subject="Password Reset Request",
        recipients=[email.email],
        body=f"Please use the following link to reset your password: {reset_url}",
        subtype="html"
    )

    fm = FastMail(conf)
    background_tasks.add_task(fm.send_message, message)
    return {"message": "Password reset email has been sent"}
@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_form(token: str, request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})
 
@app.post("/reset-password")
async def reset_password(session: Annotated[Session, Depends(get_session)], token: str = Form(...), new_password: str = Form(...)):
    email = verify_reset_token(token)
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.password = get_password_hash(new_password)
    session.add(user)
    session.commit()
    return {"message": "Password has been reset successfully"}

@app.delete("/delete-user/{user_id}", response_model=User)
async def delete_user(user_id: int, session: Annotated[Session, Depends(get_session)], current_user: User = Depends(get_current_admin_user)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(user)
    session.commit()
    return user

# To run the app use the following command
# uvicorn main:app --reload
