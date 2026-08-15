"""Build the portable single-file executable.

	python tools/build.py            -> dist/GradientDescent.exe
	python tools/build.py --dir      -> dist/GradientDescent/ (starts instantly)
	python tools/build.py --zip      -> also zip the result for sharing

One file means one thing to send someone: no install, no python, no wheels. The
cost is a few seconds of self-extraction on every launch, which --dir avoids.
"""

import os, sys, subprocess, shutil, time, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = 'GradientDescent'

# nothing here is imported by the game, but PyInstaller finds them through numpy
# and pygame and they cost tens of megabytes each
EXCLUDES = ('tkinter', 'matplotlib', 'scipy', 'PIL', 'pandas', 'IPython', 'jupyter',
            'notebook', 'pytest', 'numpy.f2py', 'numpy.testing',
            'pygame.examples', 'pygame.tests', 'pydoc_data', 'lib2to3')


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('--dir', action='store_true', help='one folder instead of one file')
	ap.add_argument('--zip', action='store_true', help='zip dist/ afterwards')
	ap.add_argument('--console', action='store_true', help='keep a console for tracebacks')
	a = ap.parse_args()

	try:
		import PyInstaller  # noqa
	except ImportError:
		print('PyInstaller is not installed. Ask for:  pip install pyinstaller')
		return 1

	ico = os.path.join(ROOT, 'misc', 'gradient.ico')
	png = os.path.join(ROOT, 'misc', 'gradient.png')
	cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
	       '--name', NAME,
	       '--onedir' if a.dir else '--onefile',
	       '--console' if a.console else '--windowed',
	       '--workpath', os.path.join(ROOT, 'build'),
	       '--distpath', os.path.join(ROOT, 'dist'),
	       '--specpath', ROOT]
	if os.path.exists(ico): cmd += ['--icon', ico]
	if os.path.exists(png): cmd += ['--add-data', png + os.pathsep + 'misc']
	for e in EXCLUDES: cmd += ['--exclude-module', e]
	cmd.append(os.path.join(ROOT, 'main.py'))

	print(' '.join(cmd), '\n')
	t0 = time.time()
	r = subprocess.run(cmd, cwd=ROOT)
	if r.returncode != 0:
		print('build failed')
		return r.returncode

	out = os.path.join(ROOT, 'dist', NAME + ('' if a.dir else '.exe'))
	if a.dir: out = os.path.join(ROOT, 'dist', NAME)
	size = 0
	if os.path.isdir(out):
		for root, _d, fs in os.walk(out):
			size += sum(os.path.getsize(os.path.join(root, f)) for f in fs)
	elif os.path.exists(out):
		size = os.path.getsize(out)
	print('\nbuilt in %.0fs   %s   %.1f MB' % (time.time() - t0, out, size / 1e6))

	if a.zip:
		base = os.path.join(ROOT, 'dist', NAME)
		if os.path.isdir(out):
			z = shutil.make_archive(base, 'zip', out)
		else:
			import zipfile
			z = base + '.zip'
			with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as f:
				f.write(out, NAME + '.exe')
		print('zipped  %s  %.1f MB' % (z, os.path.getsize(z) / 1e6))
	return 0


if __name__ == '__main__':
	sys.exit(main())
