"""Bounded, full-quality Lanczos scaling with exact integer strip boundaries."""
from concurrent.futures import ThreadPoolExecutor
import math,os
from PIL import Image


class ScreenScaler:
    def __init__(self,workers=None):
        self.workers=max(1,min(4,workers if workers is not None else (os.cpu_count() or 1)))
        self.pool=None;self.failed=False;self.previous=None;self.result=None;self.key=None
        self.last_workers=0;self.last_cached=False

    def resize(self,image,size,source_key=None,unchanged=False):
        size=tuple(size)
        if len(size)!=2 or any(type(n) is not int or n<1 for n in size):raise ValueError('Dimensões de escala inválidas.')
        key=(source_key,size,image.size,image.mode)
        if unchanged and self.previous is image and self.key==key and self.result is not None:
            self.last_cached=True;self.last_workers=0;return self.result
        self.last_cached=False;self.last_workers=1
        if image.size==size:result=image;self.last_workers=0
        else:
            # Each strip begins at an integer source row. This retains the
            # same filter phase/weights as a whole-image Lanczos resize.
            units=math.gcd(image.height,size[1]);unit_out=size[1]//units;unit_in=image.height//units
            count=min(self.workers,units)
            # Pillow 13 chooses horizontal/vertical pass order from image and
            # output dimensions, not from the box. A strip must choose the
            # same order as a whole frame, since 8-bit intermediate rounding
            # differs between orders. Otherwise retain the serial reference.
            def horizontal_first(height):
                return not (image.height-height>0 and image.height-height>(image.width-size[0])*2)
            reference_order=horizontal_first(size[1])
            while count>1 and any(horizontal_first(((i+1)*units//count-i*units//count)*unit_out)!=reference_order for i in range(count)):
                count-=1
            if self.failed or count<2 or image.width*image.height<1024*1024:
                result=image.resize(size,Image.Resampling.LANCZOS)
            else:
                image.load()  # No lazy decoder state is shared by workers.
                if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=self.workers,thread_name_prefix='Desk scale')
                bounds=[(i*units//count,(i+1)*units//count) for i in range(count)]
                futures=[self.pool.submit(image.resize,(size[0],(b-a)*unit_out),Image.Resampling.LANCZOS,
                           box=(0,a*unit_in,image.width,b*unit_in)) for a,b in bounds]
                try:
                    strips=[future.result() for future in futures]
                    result=Image.new(image.mode,size)
                    for (top,_),strip in zip(bounds,strips):result.paste(strip,(0,top*unit_out))
                    self.last_workers=count
                except Exception:
                    for future in futures:future.cancel()
                    self.pool.shutdown(wait=True,cancel_futures=True);self.pool=None;self.failed=True
                    result=image.resize(size,Image.Resampling.LANCZOS)
        self.previous=image;self.key=key;self.result=result
        return result

    def close(self):
        if self.pool:self.pool.shutdown(wait=True,cancel_futures=True);self.pool=None
        self.previous=None;self.result=None;self.key=None
