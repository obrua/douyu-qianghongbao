import setuptools
from distutils.core import setup
from Cython.Build import cythonize
from douyu_login import loginByQrcode
 
setup(
  # name = 'Hello world app',
  ext_modules = cythonize(["gethongbao.py"]),
)