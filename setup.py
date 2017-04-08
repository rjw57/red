import os
from setuptools import setup, find_packages

THIS_DIR = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(THIS_DIR, 'requirements.txt')) as f:
    install_requires = f.read().splitlines()

setup(
    name='red',
    packages=find_packages(),
    install_requires=install_requires,
    entry_points={
        'console_scripts': [
            'red=red:main',
        ],
    },
)
