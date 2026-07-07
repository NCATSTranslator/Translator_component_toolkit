from setuptools import setup, find_packages

setup(
    name='TCT',
    version='0.1.6',
    packages=find_packages(),
    install_requires=[
        # List your library's dependencies here
        'requests',
        'pandas',
        'seaborn',
        'matplotlib',
        'ipycytoscape',
        'networkx',
        'numpy',
        'openai',
        'PyYAML',
        'copy',
    ],
    entry_points={
        'console_scripts': [
            # Define any command-line scripts here
        ],
    },
    url='https://github.com/NCATSTranslator/Translator_component_toolkit',
    author='Guangrong Qin',
    author_email='guangrong.qin@isbscience.org',
    description='Translator Component Toolkit',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    license='MIT',
)
