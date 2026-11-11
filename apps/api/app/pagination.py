"""Versioned keyset cursors bound to workspace, collection and explicit order."""
import base64,json
from datetime import datetime,timezone
from sqlalchemy import or_,and_
from fastapi import HTTPException

def timestamp(value):
    if value is None:return None
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return value.isoformat()

def page(session,statement,model,workspace,collection,order,limit,offset,cursor):
    if order not in {'id_asc','created_desc'}:raise HTTPException(422,'不支持该排序')
    if cursor:
        if offset:raise HTTPException(422,'cursor和offset不能同时使用')
        try:
            if len(cursor)>2048:raise ValueError()
            data=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
            if (data['v'],data['workspace'],data['collection'],data['order'])!=(1,workspace,collection,order) or not isinstance(data['id'],str):raise ValueError()
            if order=='id_asc':statement=statement.where(model.id>data['id'])
            elif data['created_at'] is None:statement=statement.where(model.created_at.is_(None),model.id>data['id'])
            else:
                moment=datetime.fromisoformat(data['created_at'])
                if moment.tzinfo is None:raise ValueError()
                statement=statement.where(or_(model.created_at<moment,and_(model.created_at==moment,model.id>data['id']),model.created_at.is_(None)))
        except (ValueError,KeyError,TypeError):raise HTTPException(422,detail={'code':'INVALID_CURSOR'}) from None
    ordering=[model.id] if order=='id_asc' else [model.created_at.desc().nullslast(),model.id]
    rows=session.scalars(statement.order_by(*ordering).offset(offset).limit(limit+1)).all()
    has_more=len(rows)>limit;rows=rows[:limit];next_cursor=None
    if has_more:
        last=rows[-1]
        data={'v':1,'workspace':workspace,'collection':collection,'order':order,'id':last.id,'created_at':timestamp(last.created_at)}
        next_cursor=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=')
    return rows,next_cursor
