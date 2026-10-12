# Compatibility entry point; the portable build configuration lives in packaging/.
from pathlib import Path
spec = Path(SPECPATH) / 'packaging/SJTURunning.spec'
SPECPATH = str(spec.parent)
exec(compile(spec.read_text(), str(spec), 'exec'))
