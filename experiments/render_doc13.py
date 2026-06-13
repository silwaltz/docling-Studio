"""Render Doc13 page 1 to image."""
import fitz
import os

PDF = r"C:\Users\silwa\Downloads\Non-real case sample doc\Non-real case sample doc\NR Doc13-Insurancepolicy.pdf"
OUT = r"C:\Users\silwa\Downloads\Non-real case sample doc\Non-real case sample doc\doc13_p1.png"
r = fitz.open(PDF)
p = r[0]
pix = p.get_pixmap(dpi=200)
pix.save(OUT)
print("saved", OUT, pix.width, "x", pix.height)
