src = "./sandbox.txt"
dst = "./answers_072725.txt"

with open(src, "r", encoding="utf-8") as fin, \
     open(dst, "w", encoding="utf-8") as fout:
    for line in fin:
        fout.write(line.lower())