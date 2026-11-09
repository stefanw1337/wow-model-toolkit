"""Decode named D3 SBK v41 sound-bank entries with the external vgmstream CLI."""
import argparse,json,struct,subprocess,wave
from pathlib import Path
from d3_assets import Reader,require


def bank_names(path):
    reader=Reader(path);require(reader.version==41,'Expected SBK v41')
    offset,size=reader.unpack('2I',28);count=reader.unpack('I',48)[0]
    require(count>0 and size==160*count,'Unsupported SBK table')
    offset=reader.span(offset,size)
    return [reader.string(offset+i*160,128) for i in range(count)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('output');p.add_argument('--decoder',required=True)
    a=p.parse_args();out=Path(a.output).resolve();require(not out.exists(),'Use a new output directory');out.mkdir(parents=True)
    source=Path(a.source).resolve();report=[]
    for bank in source.rglob('*.sbk'):
        names=bank_names(bank)
        for file in sorted(bank.with_suffix('').glob('*')):
            if file.suffix.lower() not in ('.fsb','.ogg'):continue
            index=int(file.stem);require(index<len(names),'Missing bank sample name')
            sample=names[index];require('/' not in sample and '\\' not in sample and ':' not in sample,'Unsafe sample name')
            target=out/bank.relative_to(source).with_suffix('')/(file.stem+'-'+sample+'.wav')
            target.parent.mkdir(parents=True,exist_ok=True)
            result=subprocess.run([str(Path(a.decoder).resolve()),'-i','-o',str(target),str(file)],capture_output=True,text=True,timeout=120)
            require(result.returncode==0 and target.is_file(),'Audio decode failed: '+result.stdout+result.stderr)
            with wave.open(str(target),'rb') as wav:
                require(wav.getsampwidth()==2 and wav.getcomptype()=='NONE','Expected PCM16 WAV')
                metadata=dict(channels=wav.getnchannels(),sample_rate=wav.getframerate(),duration=wav.getnframes()/wav.getframerate())
            report.append(dict(source=str(file.relative_to(source)),name=sample,wav=str(target.relative_to(out)),**metadata))
    (out/'manifest.json').write_text(json.dumps(report,indent=2))
    print('Decoded',len(report),'audio files to',out)


if __name__=='__main__':main()
