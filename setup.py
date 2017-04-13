import os
from setuptools import setup, find_packages

THIS_DIR = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(THIS_DIR, 'requirements.txt')) as f:
    INSTALL_REQUIRES=f.read().splitlines()

setup(
    name='red',
    install_requires=INSTALL_REQUIRES,
    packages=find_packages(),
    package_data={
        'red': ['lang/*.lang'],
    },
    entry_points={
        'console_scripts': [
            'red=red:main',
        ],
    },
)
