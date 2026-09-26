import re,sys
pat=re.compile(r'<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', re.S)
mode=sys.argv[1]
for path in sys.argv[2:]:
    s=open(path).read()
    s=pat.sub(lambda m: {'both':m.group(1)+m.group(2),'ours':m.group(1),'theirs':m.group(2)}[mode], s)
    open(path,'w').write(s)
