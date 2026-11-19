from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
paths=list((root/'automatic_shift/tests').glob('*.cpp'))+[root/'tests/test_automatic_shift_adapter.cpp']
with tempfile.TemporaryDirectory() as tmp:
 for path in paths:
  binary=Path(tmp)/path.stem
  subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root),str(path),'-o',str(binary)],check=True)
  subprocess.run([str(binary)],check=True)
