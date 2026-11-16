def serialize(item):
    return {c.name:getattr(item,c.name) for c in item.__table__.columns}
def serialize_many(items): return [serialize(i) for i in items]
def serialize_report(item,stale=False):
    data=serialize(item);data['stale']=stale
    return data
