import hashlib, hmac, secrets, time, uuid
from urllib.parse import urlsplit
from fastapi import HTTPException, Request, Response
from sqlalchemy import String, Float, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, Session
class Account(Base):
    __tablename__='accounts'
    username:Mapped[str]=mapped_column(String,primary_key=True)
    workspace:Mapped[str]=mapped_column(String)
    password_hash:Mapped[str]=mapped_column(String)
class LoginSession(Base):
    __tablename__='sessions'
    digest:Mapped[str]=mapped_column(String,primary_key=True)
    workspace:Mapped[str]=mapped_column(String)
    csrf:Mapped[str]=mapped_column(String)
    expires:Mapped[float]=mapped_column(Float)
def password_hash(password,salt=None):
    if len(password)<12:raise ValueError('密码至少12位')
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def authenticate(request:Request):
    token=request.cookies.get('aigc_session','')
    with Session() as s:
        row=s.get(LoginSession,hashlib.sha256(token.encode()).hexdigest())
        if not row or row.expires<time.time():raise HTTPException(401,'请登录')
        if request.method not in {'GET','HEAD','OPTIONS'} and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),row.csrf):raise HTTPException(403,'CSRF校验失败')
        return row.workspace
from .auth_limits import consume
# Compatibility for existing test fixtures; production enforcement is persisted.
attempts={}


def require_session_origin(request):
    origins=request.headers.getlist('origin')
    if not origins:
        return
    try:
        if len(origins)!=1 or any(character.isspace() for character in origins[0]):
            raise ValueError
        origin=urlsplit(origins[0])
        target=urlsplit(str(request.url))
        if origin.scheme not in ('http','https') or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username is not None:
            raise ValueError
        def address(url):
            port=url.port if url.port is not None else (443 if url.scheme=='https' else 80)
            return url.scheme,url.hostname,port
        if address(origin)!=address(target):
            raise ValueError
    except ValueError:
        raise HTTPException(403,detail={'code':'ORIGIN_REJECTED','message':'请求来源无效'}) from None


def add_session(session,workspace):
    token=secrets.token_urlsafe(32)
    csrf=secrets.token_urlsafe(32)
    session.add(LoginSession(digest=hashlib.sha256(token.encode()).hexdigest(),
        workspace=workspace,csrf=csrf,expires=time.time()+28800))
    return token,csrf


def session_response(request,response,token,csrf):
    response.set_cookie('aigc_session',token,httponly=True,samesite='strict',
        secure=request.url.scheme=='https',max_age=28800)
    return {'csrf_token':csrf}


def register(username,password,request,response):
    require_session_origin(request)
    if not username.isprintable() or username!=username.strip():
        raise HTTPException(422,detail={'code':'USERNAME_INVALID','message':'用户名不能含首尾空格或控制字符'})
    ip=request.client.host if request.client else 'unknown'
    allowed,retry=consume('register-ip',ip)
    if not allowed:
        raise HTTPException(429,'请稍后重试',headers={'Retry-After':str(retry)})
    workspace=str(uuid.uuid4())
    with Session() as session:
        account=Account(username=username,workspace=workspace,password_hash=password_hash(password))
        try:
            session.add(account)
            session.flush()
            token,csrf=add_session(session,workspace)
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.get(Account,username) is None:
                raise
            raise HTTPException(409,detail={'code':'USERNAME_TAKEN','message':'该用户名已注册'}) from None
    return session_response(request,response,token,csrf)


def login(username,password,request,response):
    require_session_origin(request)
    key=request.client.host if request.client else 'unknown'
    ip_allowed,ip_retry=consume('ip',key)
    account_allowed,account_retry=consume('account',username.casefold())
    if not ip_allowed or not account_allowed:raise HTTPException(429,'请稍后重试',headers={'Retry-After':str(max(ip_retry,account_retry))})
    with Session() as s:
        account=s.get(Account,username)
        try: valid=account and hmac.compare_digest(password_hash(password,account.password_hash.split(':')[0]),account.password_hash)
        except ValueError:valid=False
        if not valid:raise HTTPException(401,'用户名或密码错误')
        token,csrf=add_session(s,account.workspace)
        s.commit()
    return session_response(request,response,token,csrf)
