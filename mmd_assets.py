"""Dependency-free PMX geometry and VMD bone-motion readers.

Exports are intermediate Wavefront OBJ and JSON, not game-ready ASP/PRS.
"""
from __future__ import annotations

import json
import math
import struct
from collections import defaultdict
from pathlib import Path


class MmdFormatError(ValueError):
    pass


class Reader:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = self.path.open('rb')
        self.size = self.path.stat().st_size

    def __enter__(self): return self
    def __exit__(self, *_): self.stream.close()

    def take(self, size):
        if not 0 <= size <= 256_000_000:
            raise MmdFormatError('Invalid data length')
        result = self.stream.read(size)
        if len(result) != size:
            raise MmdFormatError('Truncated file at offset ' + str(self.stream.tell()))
        return result

    def unpack(self, fmt): return struct.unpack('<'+fmt, self.take(struct.calcsize('<'+fmt)))
    def i32(self): return self.unpack('i')[0]
    def u32(self): return self.unpack('I')[0]
    def u16(self): return self.unpack('H')[0]
    def u8(self): return self.unpack('B')[0]
    def f32(self): return self.unpack('f')[0]

    def indexed(self, size, signed=True):
        if size not in (1,2,4): raise MmdFormatError('Bad index width')
        return int.from_bytes(self.take(size), 'little', signed=signed)

    def count(self, *, maximum=4_000_000):
        count = self.i32()
        if not 0 <= count <= maximum: raise MmdFormatError('Unreasonable element count')
        return count

    def text(self, encoding):
        size = self.count(maximum=20_000_000)
        if size > 0 and encoding == 'utf-16-le' and size % 2:
            raise MmdFormatError('Odd UTF16 string size')
        return self.take(size).decode(encoding, errors='replace')


def read_pmx(path):
    """Read PMX 2.0/2.1 visible mesh, UVs, texture names, materials and bones."""
    with Reader(path) as r:
        if r.take(4) != b'PMX ': raise MmdFormatError('Not a PMX file')
        version = r.f32()
        if not 1.99 <= version <= 2.11: raise MmdFormatError('Unsupported PMX version')
        n = r.u8()
        if not 8 <= n <= 64: raise MmdFormatError('Bad PMX header length')
        options = r.take(n)
        if options[0] not in (0,1) or options[1] > 4:
            raise MmdFormatError('Unsupported PMX settings')
        encoding = 'utf-16-le' if options[0] == 0 else 'utf-8'
        add_uv = options[1]
        vi,ti,mi,bi = options[2],options[3],options[4],options[5]
        if any(x not in (1,2,4) for x in options[2:8]):
            raise MmdFormatError('Unsupported PMX index widths')
        name, english_name, comment, english_comment = (r.text(encoding) for _ in range(4))
        verts, uvs = [], []
        for _ in range(r.count(maximum=2_000_000)):
            verts.append(r.unpack('3f'))
            r.take(12)
            uvs.append(r.unpack('2f'))
            r.take(16*add_uv)
            deform = r.u8()
            if deform == 0: r.take(bi)
            elif deform == 1: r.take(bi*2+4)
            elif deform in (2,4): r.take(bi*4+16)
            elif deform == 3: r.take(bi*2+40)
            else: raise MmdFormatError('Unsupported deform type '+str(deform))
            r.take(4)
        face_len = r.count(maximum=12_000_000)
        if face_len % 3: raise MmdFormatError('Face index count is not divisible by three')
        indices = [r.indexed(vi, signed=False) for _ in range(face_len)]
        if any(v >= len(verts) for v in indices):
            raise MmdFormatError('Face index beyond vertex count')
        textures = [r.text(encoding) for _ in range(r.count(maximum=200_000))]
        materials = []
        covered = 0
        for _ in range(r.count(maximum=100_000)):
            mat_name, mat_english = r.text(encoding), r.text(encoding)
            r.take(16+12+4+12+1+16+4)
            tex_id = r.indexed(ti)
            r.take(ti)
            r.take(1)
            if r.u8(): r.take(1)
            else: r.take(ti)
            r.text(encoding)
            nfaces = r.count(maximum=face_len)
            if nfaces % 3: raise MmdFormatError('Material surface count not divisible by 3')
            covered += nfaces
            materials.append({'name':mat_english or mat_name or 'Material', 'texture_index':tex_id, 'index_count':nfaces})
        if covered != face_len: raise MmdFormatError('Materials do not cover all faces')
        bones=[]
        for _ in range(r.count(maximum=200_000)):
            bname = r.text(encoding)
            ename = r.text(encoding)
            pos = r.unpack('3f')
            parent = r.indexed(bi)
            r.i32()
            flags = r.u16()
            if flags & 0x0001: r.take(bi)
            else: r.take(12)
            if flags & 0x0300: r.take(bi+4)
            if flags & 0x0400: r.take(12)
            if flags & 0x0800: r.take(24)
            if flags & 0x2000: r.take(4)
            if flags & 0x0020:
                r.take(bi+4+4)
                for _ in range(r.count(maximum=10_000)):
                    r.take(bi)
                    if r.u8(): r.take(24)
            bones.append({'name': bname, 'english_name':ename, 'position':pos, 'parent':parent})
        return {'format':'pmx', 'version':round(version,1), 'name': english_name or name,
                'vertices': verts, 'uvs':uvs, 'indices':indices,
                'textures': textures, 'materials':materials, 'bones':bones}


def inspect_pmd(path):
    """Read PMD header only; geometry export requires a PMD->PMX conversion."""
    with Reader(path) as r:
        if r.take(3) != b'Pmd': raise MmdFormatError('Not a PMD file')
        version = r.f32()
        name = r.take(20).split(b'\0',1)[0].decode('cp932', errors='replace')
        comment = r.take(256).split(b'\0',1)[0].decode('cp932', errors='replace')
        vertex_count = r.u32()
        if vertex_count > 2_000_000: raise MmdFormatError('Unreasonable PMD vertex count')
        return {'format':'pmd','version':round(version,2),'name':name,'vertex_count':vertex_count,'comment':comment}


def read_vmd(path):
    """Read VMD v1/v2 bone keyframes, preserving interpolation bytes."""
    with Reader(path) as r:
        header = r.take(30)
        if header.startswith(b'Vocaloid Motion Data 0002'):
            model_size = 20
        elif header.startswith(b'Vocaloid Motion Data file'):
            model_size = 10
        else: raise MmdFormatError('Invalid VMD signature')
        name = r.take(model_size).split(b'\0',1)[0].decode('cp932',errors='replace')
        count = r.u32()
        if count > 4_000_000: raise MmdFormatError('Unreasonable keyframe count')
        tracks = defaultdict(list)
        end = 0
        for _ in range(count):
            raw = r.take(15)
            bone = raw.split(b'\0',1)[0].decode('cp932',errors='replace')
            frame = r.u32()
            if frame > 10_000_000: raise MmdFormatError('Unreasonable frame number')
            xyz = r.unpack('3f')
            xyzw = r.unpack('4f')
            curves = r.take(64).hex()
            if not all(math.isfinite(n) for n in xyz+xyzw):
                raise MmdFormatError('Nonfinite motion data')
            tracks[bone].append({'frame':frame,'position':xyz,'quaternion':xyzw,'interpolation_hex':curves})
            end = max(end,frame)
        return {'format':'vmd','model_name':name,'frame_rate':30,'frame_count':end+1 if count else 0,
                'keyframe_count':count,'tracks':dict(tracks)}


def export_obj(pmx_file, destination):
    """Export neutral OBJ+MTL; does NOT preserve a skinned game-ready skeleton."""
    data=read_pmx(pmx_file)
    dest=Path(destination)
    dest.parent.mkdir(parents=True,exist_ok=True)
    mtl=dest.with_suffix('.mtl')
    def clean_name(s): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in s)[:64] or 'Material'
    mat_names=[f'{i}_{clean_name(m["name"])}' for i,m in enumerate(data['materials'])]
    with dest.open('w',encoding='utf-8',newline='\n') as f:
        f.write('# Neutral PMX mesh export. This is NOT a DS2 ASP asset.\nmtllib '+mtl.name+'\n')
        for v in data['vertices']:f.write('v {:.8g} {:.8g} {:.8g}\n'.format(*v))
        for uv in data['uvs']:f.write('vt {:.8g} {:.8g}\n'.format(uv[0],1-uv[1]))
        offset=0
        for n,mat in zip(mat_names,data['materials']):
            f.write('usemtl '+n+'\n')
            for j in range(offset,offset+mat['index_count'],3):
                inds=[data['indices'][j+k]+1 for k in range(3)]
                f.write('f '+' '.join(f'{idx}/{idx}' for idx in inds)+'\n')
            offset+=mat['index_count']
    with mtl.open('w',encoding='utf-8',newline='\n') as f:
        for n,mat in zip(mat_names,data['materials']):
            f.write('newmtl '+n+'\nKd 1 1 1\n')
            t=mat['texture_index']
            if 0<=t<len(data['textures']):
                tex=data['textures'][t].replace('\\','/')
                if '..' not in Path(tex).parts and not Path(tex).is_absolute():
                    f.write('map_Kd '+tex.replace('\n','')+'\n')
    bones_file=dest.with_suffix('.bones.json')
    bones_file.write_text(json.dumps({'model':data['name'],'bones':data['bones']},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'obj':str(dest),'mtl':str(mtl),'bones':str(bones_file),
            'vertex_count':len(data['vertices']),'triangle_count':len(data['indices'])//3,
            'bone_count':len(data['bones'])}


def export_motion(vmd_file,destination,bone_map=None):
    """Export keyed bone tracks to intermediate JSON, not PRS."""
    data=read_vmd(vmd_file)
    bone_map=bone_map or {}
    if len(set(bone_map.values()))!=len(bone_map.values()):
        raise MmdFormatError('Multiple MMD bones mapped to the same target bone')
    tracks={}
    for bone,keys in data['tracks'].items():
        target=bone_map.get(bone,bone)
        if target in tracks:raise MmdFormatError('Bone mapping collision: '+target)
        tracks[target]=keys
    data['tracks']=tracks
    data['retargeting_status']='NAME_MAPPING_ONLY; no coordinate or rest-pose corrections applied'
    Path(destination).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'track_count':len(tracks),'keyframe_count':data['keyframe_count'],'duration_seconds':round(max(0,data['frame_count']-1)/30,3)}
