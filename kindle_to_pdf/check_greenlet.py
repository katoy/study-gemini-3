import traceback
import sys
print('Python:', sys.version)
try:
    import greenlet
    print('greenlet module:', greenlet)
    print('__file__:', getattr(greenlet, '__file__', None))
    print('__version__:', getattr(greenlet, '__version__', None))
except Exception as e:
    print('IMPORT ERROR:')
    traceback.print_exc()
    sys.exit(1)
print('OK')
