"""Symbolise eu-stack addresses offline: python3 symbolize.py <maps-line-base-hex for x11vnc> <libvncserver base> addr addr ..."""
import sys, bisect
from elftools.elf.elffile import ELFFile

def load_syms(path):
    syms = []
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        for secname in ('.symtab', '.dynsym'):
            sec = elf.get_section_by_name(secname)
            if sec is None: continue
            for s in sec.iter_symbols():
                if s['st_info']['type'] == 'STT_FUNC' and s['st_value']:
                    syms.append((s['st_value'], s.name))
        # file offset of the first PT_LOAD for the executable segment vs vaddr: compute load bias
        segs = [p for p in elf.iter_segments() if p['p_type'] == 'PT_LOAD']
        bias = segs[0]['p_vaddr'] - segs[0]['p_offset']
    syms.sort()
    return syms, bias

MODS = {
  'x11vnc': ('root/usr/lib/debug/.build-id/b1/6dc20339b47925697778a154bafb9a688828ca.debug', 'root/usr/bin/x11vnc'),
  'libvncserver': ('root/usr/lib/x86_64-linux-gnu/libvncserver.so.0.9.14', None),
}
def nearest(syms, addr):
    i = bisect.bisect_right(syms, (addr, '\xff')) - 1
    if i < 0: return '?'
    return f"{syms[i][1]}+0x{addr - syms[i][0]:x}"

if __name__ == '__main__':
    # args: module=base_hex ... then addresses
    bases = {}; addrs = []
    for a in sys.argv[1:]:
        if '=' in a: k, v = a.split('='); bases[k] = int(v, 16)
        else: addrs.append(int(a, 16))
    cache = {}
    for mod, base in bases.items():
        path = MODS[mod][0]
        cache[mod] = load_syms(path)
    for addr in addrs:
        best = None
        for mod, base in bases.items():
            syms, bias = cache[mod]
            if addr >= base:
                off = addr - base + bias  # assumes r-xp map starts at file offset 0; refine with map offset if not
                cand = (mod, nearest(syms, off))
                if best is None or addr - base < addr - bases[best[0]]: best = cand
        print(hex(addr), best)
