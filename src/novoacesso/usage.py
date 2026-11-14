"""Limite conservador e persistente de bytes retransmitidos, por mês UTC."""
import datetime,json,math,os,tempfile,threading
from pathlib import Path

class MonthlyBudget:
    def __init__(self,path,limit,clock=None):
        self.path=Path(path);self.limit=int(limit);self.clock=clock or (lambda:datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m'))
        if self.limit<=0:raise ValueError('Limite mensal deve ser positivo.')
        self.lock=threading.Lock();self.month=self.clock();self.used=0;self.reserved=0
        if self.path.exists():
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data['month']==self.month:self.used=self.reserved=int(data['reserved'])
    def _save(self,value):
        with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as out:
            out.write(json.dumps(dict(month=self.month,reserved=value)).encode());out.flush();os.fsync(out.fileno());tmp=Path(out.name)
        try:tmp.chmod(0o600);tmp.replace(self.path)
        finally:tmp.unlink(missing_ok=True)
    def allow(self,size):
        if type(size) is not int or size<0:raise ValueError('Quantidade de bytes inválida.')
        with self.lock:
            month=self.clock()
            if month!=self.month:self.month=month;self.used=self.reserved=0;self._save(0)
            if self.used+size>self.limit:return False
            if self.used+size>self.reserved:
                reserve=min(self.limit,math.ceil((self.used+size)/(1024*1024))*1024*1024)
                self._save(reserve);self.reserved=reserve
            self.used+=size;return True
