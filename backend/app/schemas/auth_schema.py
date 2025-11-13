from pydantic import BaseModel, Field, EmailStr

class RegisterSchema(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="teacher")

class LoginSchema(BaseModel):
    username: str
    password: str
