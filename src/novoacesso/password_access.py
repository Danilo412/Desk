"""Owner-configured password access, verified only inside pinned encrypted sessions."""
import hashlib,secrets,threading,time
from .wire import AuthorizationError

def password_bytes(value):
    if not isinstance(value,str) or not 12<=len(value)<=128:raise ValueError('Use uma senha de acesso com 12 a 128 caracteres.')
    raw=value.encode('utf-8')
    if len(raw)>512:raise ValueError('A senha de acesso é muito longa.')
    return raw

def derive(raw,salt):
    return hashlib.scrypt(raw,salt=salt,n=32768,r=8,p=1,maxmem=64*1024*1024,dklen=32)

class PasswordAccess:
    def __init__(self,identity,clock=time.monotonic):
        self.identity=identity;self.clock=clock;self.failures=[];self.attempt_lock=threading.Lock()
    def snapshot(self):
        with self.identity.lock:return dict(self.identity.data.get('password_access',{}))
    def information(self):
        record=self.snapshot()
        configured=self.valid_record(record)
        return dict(configured=configured,enabled=configured and record.get('enabled') is True,revision=record.get('revision',0))
    @staticmethod
    def valid_record(record):
        try:
            return (record.get('v')==1 and type(record.get('revision')) is int and record['revision']>0 and
                    isinstance(record.get('salt'),str) and len(record['salt'])==32 and len(bytes.fromhex(record['salt']))==16 and
                    isinstance(record.get('verifier'),str) and len(record['verifier'])==64 and len(bytes.fromhex(record['verifier']))==32)
        except (ValueError,TypeError):return False
    def set_password(self,value):
        raw=password_bytes(value);salt=secrets.token_bytes(16);verifier=derive(raw,salt).hex()
        with self.identity.lock:
            revision=self.identity.data.get('password_access',{}).get('revision',0)+1
            self.identity.data['password_access']=dict(v=1,salt=salt.hex(),verifier=verifier,revision=revision,enabled=False)
            self.identity.save()
    def enable(self,enabled):
        with self.identity.lock:
            record=self.snapshot()
            if enabled and not self.valid_record(record):raise ValueError('Defina a senha de acesso primeiro.')
            record['enabled']=bool(enabled);record['revision']=record.get('revision',0)+1
            self.identity.data['password_access']=record;self.identity.save()
    def remove(self):
        with self.identity.lock:
            revision=self.identity.data.get('password_access',{}).get('revision',0)+1
            self.identity.data['password_access']=dict(revision=revision,enabled=False);self.identity.save()
    def authorized(self,revision):
        current=self.information()
        return current['enabled'] and current['revision']==revision
    def verify(self,value):
        # One bounded KDF at a time, shared by invitations from this app instance.
        # A successful login does not erase preceding failed attempts.
        with self.attempt_lock:
            now=self.clock();self.failures=[t for t in self.failures if now-t<300]
            if len(self.failures)>=5:raise AuthorizationError('Acesso por senha temporariamente limitado. Aguarde cinco minutos.')
            record=self.snapshot();accepted=False
            try:
                raw=password_bytes(value)
                if self.valid_record(record) and record.get('enabled') is True:
                    accepted=secrets.compare_digest(derive(raw,bytes.fromhex(record['salt'])),bytes.fromhex(record['verifier']))
            except (ValueError,TypeError,UnicodeError):pass
            if not accepted or not self.authorized(record.get('revision')):
                self.failures.append(now)
                raise AuthorizationError('Senha incorreta ou acesso por senha desativado no computador remoto.')
            return record['revision']
