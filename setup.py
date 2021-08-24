import os
import re
import sys
from setuptools import setup, find_packages


__version__ = None
exec(open('conductor/version.py').read())


def valid_requirement(req):
    return not (re.match(r'^\s*$', req) or re.match('^#', req))


requirements_txt = open('requirements.txt').read().splitlines()
requirements = [req for req in requirements_txt if valid_requirement(req)]

extras_require = {
    'postgres': 'psycopg2',
}

setup(
    name='conductor',
    version=__version__,
    author='Milosz Wasilewski',
    author_email='milosz.wasilewski@foundries.io',
    url='https://github.com/foundriesio/conductor',
    packages=find_packages(exclude=['test*']),
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'conductor-admin=conductor.manage:main',
            'conductor-ws=conductor.run.websockets:main',
            'conductor-worker=conductor.run.worker:main',
            'conductor-listener=conductor.run.listener:main',
        ]
    },
    scripts=["conductor/scripts/checkout_repository.sh",
        "conductor/scripts/merge_manifest.sh",
        "conductor/scripts/upgrade_commit.sh"],
    install_requires=requirements,
    extras_require=extras_require,
    license='Apache License 2.0',
    description="Foundries.io test scheduler/coordinator",
    platforms='any',
)
