## Run Python tests against multiple installations of OpenSSL and LibreSSL

```
git clone https://github.com/python/cpython.git
git clone https://github.com/tiran/multissl.git
cd cpython
./configure
make
./python ../multissl/multissl.py
```
