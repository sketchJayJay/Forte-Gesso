import os, sqlite3, secrets, json, csv, io
from datetime import date, datetime
from functools import wraps
from flask import Flask, request, jsonify, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.secret_key=os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY']=True
app.config['SESSION_COOKIE_SAMESITE']='Lax'
app.config['SESSION_COOKIE_SECURE']=os.environ.get('COOKIE_SECURE','0')=='1'
DB=os.environ.get('DATABASE_PATH','/data/fortegesso.db' if os.path.isdir('/data') else 'fortegesso.db')

def conn():
    c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL');return c

def init():
    os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS bank_opening(id INTEGER PRIMARY KEY CHECK(id=1),amount REAL NOT NULL DEFAULT 0,start_date TEXT NOT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT DEFAULT '',address TEXT DEFAULT '',notes TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,title TEXT NOT NULL,description TEXT DEFAULT '',job_date TEXT DEFAULT '',status TEXT DEFAULT 'agendado',price REAL DEFAULT 0,helper TEXT DEFAULT '',helper_cost REAL DEFAULT 0,notes TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,title TEXT NOT NULL,items TEXT DEFAULT '[]',total REAL DEFAULT 0,status TEXT DEFAULT 'pendente',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,kind TEXT NOT NULL,description TEXT NOT NULL,amount REAL NOT NULL,method TEXT DEFAULT 'pix',due_date TEXT DEFAULT '',paid_date TEXT DEFAULT '',status TEXT DEFAULT 'pendente',cheque_number TEXT DEFAULT '',cheque_bank TEXT DEFAULT '',cheque_holder TEXT DEFAULT '',notes TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS ix_movements_job ON movements(job_id);
        CREATE INDEX IF NOT EXISTS ix_movements_date ON movements(due_date);
        ''')
        if not c.execute('SELECT id FROM users LIMIT 1').fetchone():
            c.execute('INSERT INTO users(username,password) VALUES(?,?)',(os.environ.get('ADMIN_USER','admin'),generate_password_hash(os.environ.get('ADMIN_PASSWORD','admin123'))))
init()

def logged(f):
    @wraps(f)
    def go(*a,**kw):
        if not session.get('uid'):return jsonify(error='Faça login novamente.'),401
        return f(*a,**kw)
    return go

def rows(q,args=()):
    with conn() as c:return [dict(x) for x in c.execute(q,args)]

def one(q,args=()):
    with conn() as c:
        x=c.execute(q,args).fetchone();return dict(x) if x else None

def val(data,k,default=''):
    x=data.get(k,default);return default if x is None else x

def numeric(x):
    try:
        n=float(x or 0)
        if not -1e12<n<1e12:raise ValueError()
        return round(n,2)
    except (ValueError,TypeError):raise ValueError('Valor numérico inválido')

TABLES={
 'clients':('name','phone','address','notes'),
 'jobs':('client_id','title','description','job_date','status','price','helper','helper_cost','notes'),
 'quotes':('client_id','title','items','total','status'),
 'movements':('job_id','client_id','kind','description','amount','method','due_date','paid_date','status','cheque_number','cheque_bank','cheque_holder','notes')
}
ALLOWED={'jobs':{'status':{'agendado','andamento','concluido','cancelado'}},'quotes':{'status':{'pendente','aprovado','recusado'}},'movements':{'kind':{'receita','material','despesa','ajudante'},'method':{'pix','dinheiro','transferencia','cartao','cheque','outro'},'status':{'pendente','pago','cancelado'}}}

def clean(table,d):
    out={}
    for k in TABLES[table]:
        if k not in d:continue
        v=d[k]
        if k in ('client_id','job_id'):
            v=int(v) if v not in ('',None,0,'0') else None
        elif k in ('price','helper_cost','total','amount'):v=numeric(v)
        elif k=='items':
            if not isinstance(v,list):raise ValueError('Itens precisam ser uma lista')
            v=json.dumps(v,ensure_ascii=False)
        else:v=str(v or '').strip()[:3000]
        if k in ALLOWED.get(table,{}) and v not in ALLOWED[table][k]:raise ValueError('Opção inválida: '+k)
        out[k]=v
    if table=='movements':
        kind=out.get('kind',d.get('kind',''));method=out.get('method',d.get('method','pix'))
        status=out.get('status',d.get('status','pendente'))
        if kind and kind not in ALLOWED['movements']['kind']:raise ValueError('Categoria inválida')
        if 'amount' in out and out['amount']<=0:raise ValueError('Valor precisa ser maior que zero')
        if method!='cheque':out.update(cheque_number='',cheque_bank='',cheque_holder='')
        if status=='pago' and not (out.get('paid_date') or d.get('paid_date')):out['paid_date']=date.today().isoformat()
        if status!='pago':out['paid_date']=''
    return out

@app.route('/api/login',methods=['POST'])
def login():
    d=request.get_json(silent=True) or {};u=one('SELECT * FROM users WHERE username=?',(d.get('username'),))
    if not u or not check_password_hash(u['password'],d.get('password','')):return jsonify(error='Usuário ou senha incorretos'),401
    session.clear();session['uid']=u['id'];return jsonify(ok=True,user=u['username'])

@app.route('/api/logout',methods=['POST'])
def logout():session.clear();return jsonify(ok=True)

@app.route('/api/me')
def me():return jsonify(authenticated=bool(session.get('uid')))

@app.route('/api/<table>',methods=['GET','POST'])
@logged
def resource(table):
    if table not in TABLES:return jsonify(error='Recurso não encontrado'),404
    if request.method=='GET':
        result=rows('SELECT * FROM '+table+' ORDER BY id DESC')
        if table=='quotes':
            for r in result:
                try:r['items']=json.loads(r['items'])
                except:r['items']=[]
        return jsonify(result)
    try:
        d=request.get_json(force=True);payload=clean(table,d)
        required={'clients':'name','jobs':'title','quotes':'title','movements':'description'}[table]
        if not payload.get(required):raise ValueError('Preencha o campo obrigatório')
        if table=='movements' and not payload.get('kind'):raise ValueError('Selecione a categoria')
        keys=list(payload)
        with conn() as c:cur=c.execute('INSERT INTO '+table+' ('+','.join(keys)+') VALUES ('+','.join('?' for x in keys)+')',tuple(payload.values()))
        return jsonify(ok=True,id=cur.lastrowid)
    except (ValueError,sqlite3.IntegrityError) as e:return jsonify(error=str(e)),400

@app.route('/api/<table>/<int:ident>',methods=['PUT','DELETE'])
@logged
def item(table,ident):
    if table not in TABLES:return jsonify(error='Recurso não encontrado'),404
    if not one('SELECT id FROM '+table+' WHERE id=?',(ident,)):return jsonify(error='Registro não encontrado'),404
    try:
        with conn() as c:
            if request.method=='DELETE':c.execute('DELETE FROM '+table+' WHERE id=?',(ident,))
            else:
                payload=clean(table,request.get_json(force=True))
                if payload:c.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in payload)+' WHERE id=?',(*payload.values(),ident))
        return jsonify(ok=True)
    except (ValueError,sqlite3.IntegrityError) as e:return jsonify(error=str(e)),400

@app.route('/api/opening-balance',methods=['GET','PUT'])
@logged
def opening_balance():
    if request.method=='GET':
        return jsonify(one('SELECT amount,start_date FROM bank_opening WHERE id=1') or {'amount':0,'start_date':date.today().isoformat(),'configured':False})
    try:
        d=request.get_json(force=True)
        amount=numeric(d.get('amount'))
        start=str(d.get('start_date',''))
        date.fromisoformat(start)
        with conn() as c:
            c.execute('INSERT INTO bank_opening(id,amount,start_date) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET amount=excluded.amount,start_date=excluded.start_date,updated_at=CURRENT_TIMESTAMP',(amount,start))
        return jsonify(ok=True)
    except (ValueError,TypeError):return jsonify(error='Informe um valor e uma data válidos.'),400

@app.route('/api/summary')
@logged
def summary():
    month=request.args.get('month',date.today().strftime('%Y-%m'))
    if len(month)!=7 or month[4]!='-':return jsonify(error='Mês inválido'),400
    ms=rows('SELECT * FROM movements WHERE substr(CASE WHEN status="pago" THEN paid_date ELSE due_date END,1,7)=?',(month,))
    totals={k:0 for k in ('receita','material','despesa','ajudante')};received=0;spent=0;to_receive=0;to_pay=0
    for m in ms:
        if m['status']=='cancelado':continue
        if m['status']=='pago':
            totals[m['kind']]+=m['amount']
            if m['kind']=='receita':received+=m['amount']
            else:spent+=m['amount']
        elif m['kind']=='receita':to_receive+=m['amount']
        else:to_pay+=m['amount']
    all_pending=rows('SELECT kind,amount FROM movements WHERE status="pendente"')
    opening=one('SELECT amount,start_date FROM bank_opening WHERE id=1')
    opening_amount=opening['amount'] if opening else 0
    start=opening['start_date'] if opening else '0000-01-01'
    bank_entries=rows('SELECT kind,amount FROM movements WHERE status="pago" AND paid_date>=? AND paid_date<=?',(start,date.today().isoformat()))
    bank_balance=round(opening_amount+sum(x['amount'] if x['kind']=='receita' else -x['amount'] for x in bank_entries),2)
    return jsonify(bank_balance=bank_balance,opening_amount=opening_amount,opening_date=start,month=month,totals=totals,received=received,spent=spent,profit=round(received-spent,2),to_receive=round(sum(x['amount'] for x in all_pending if x['kind']=='receita'),2),to_pay=round(sum(x['amount'] for x in all_pending if x['kind']!='receita'),2),month_to_receive=to_receive,month_to_pay=to_pay,active_jobs=one('SELECT count(*) AS n FROM jobs WHERE status IN ("agendado","andamento")')['n'],client_count=one('SELECT count(*) AS n FROM clients')['n'])

@app.route('/api/export')
@logged
def export():
    table=request.args.get('table','movements')
    if table not in TABLES:return jsonify(error='Tabela inválida'),400
    data=rows('SELECT * FROM '+table+' ORDER BY id DESC');s=io.StringIO();w=csv.writer(s,delimiter=';');w.writerow(['id',*TABLES[table]])
    for r in data:w.writerow([r.get(k,'') for k in ['id',*TABLES[table]]])
    return Response('\ufeff'+s.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename={table}.csv'})

@app.route('/api/password',methods=['POST'])
@logged
def password():
    d=request.get_json(force=True);u=one('SELECT * FROM users WHERE id=?',(session['uid'],))
    if not check_password_hash(u['password'],d.get('old','')):return jsonify(error='Senha atual incorreta'),400
    if len(d.get('new',''))<8:return jsonify(error='Use pelo menos 8 caracteres'),400
    with conn() as c:c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(d['new']),session['uid']))
    return jsonify(ok=True)

@app.route('/logo.jpg')
def logo():return send_file('logo.jpg')

@app.route('/manifest.json')
def manifest():return jsonify(name='Forte Gesso | Gestão',short_name='Forte Gesso',display='standalone',start_url='/',background_color='#090b1d',theme_color='#131131',icons=[{'src':'/logo.jpg','sizes':'any','type':'image/jpeg','purpose':'any'}])

@app.route('/')
def index():return send_file('index.html')

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
