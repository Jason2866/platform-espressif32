import ctypes
import sys
import locale

codepage = ctypes.windll.kernel32.GetConsoleOutputCP()

print("Aktive Codepage (Windows kernel32):", codepage)
print("Encoding für Standardausgabe (stdout):", sys.stdout.encoding)
print("Encoding für Standardeingabe (stdin):", sys.stdin.encoding)
print("Bevorzugtes Encoding laut System:", locale.getpreferredencoding())
