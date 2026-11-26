"""Controle conservador de carga: preserva resolução, adapta FPS e vídeo."""
import threading,time

class AdaptiveQuality:
    def __init__(self):
        self.lock=threading.Lock();self.target_fps=30;self.delay_ms=0.;self.rtt_ms=0.;self.encode_ms=0.;self.factor=1.;self.updated=0.;self.healthy=0
    def feedback(self,delay_ms=None,rtt_ms=None):
        with self.lock:
            if delay_ms is not None:
                sample=max(0,min(10000,delay_ms));self.delay_ms=sample if not self.delay_ms else .7*self.delay_ms+.3*sample
            if rtt_ms is not None:
                sample=max(0,min(10000,rtt_ms));self.rtt_ms=sample if not self.rtt_ms else .7*self.rtt_ms+.3*sample
    def observe(self,requested,encode_ms,backlog,now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            self.encode_ms=.8*self.encode_ms+.2*encode_ms
            if self.target_fps>requested:self.target_fps=requested
            if now-self.updated>=1:
                # O ACK do quadro já inclui a ida e volta. Uma rota distante
                # não deve permitir vários segundos adicionais de fila.
                queued_delay=self.delay_ms-self.rtt_ms
                overloaded=backlog>=2 or (self.delay_ms>350 and queued_delay>250) or self.encode_ms>1000/max(1,self.target_fps)*.9
                if overloaded:
                    # Preserve spatial detail. Reducing bitrate together with
                    # FPS made every busy period progressively blurrier.
                    self.target_fps=max(8,min(requested,int(self.target_fps*.8)));self.healthy=0
                else:
                    self.healthy+=1
                    if self.healthy>=2:self.target_fps=min(requested,self.target_fps+4);self.healthy=0
                self.updated=now
            return max(1,min(requested,self.target_fps)),self.factor
    def snapshot(self):
        with self.lock:return dict(delivery_ms=round(self.delay_ms,1),rtt_ms=round(self.rtt_ms,1),encode_ms=round(self.encode_ms,1),effective_fps=self.target_fps,video_factor=round(self.factor,2))
