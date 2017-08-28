::install choco
::@"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
choco install python3 -y
choco install git -y
::refreshenv
choco install visualstudio2017community -y -packageParameters "--allWorkloads --includeRecommended --includeOptional --passive"
git clone --recursive https://github.com/thp/psmoveapi.git
choco install cmake --installargs 'ADD_CMAKE_TO_PATH=""User""' -y
set path=C:\Program Files\CMake\bin;%path%
choco install microsoft-build-tools -y
choco install visualcpp-build-tools -y
pip install numpy
choco install swig -y
choco install cmake -y
::set PATH=%PATH%;C:\Program Files (x86)\Microsoft Visual Studio\2017\BuildTools\MSBuild\15.0\Bin
::set PATH="C:\Program Files\CMake\bin\";%PATH%
set PYTHONPATH="C:\Users\Aaron\Documents\GitHub\JoustMania\psmoveapi\build\Release";%PYTHONPATH%
psmoveapi/scripts/visualc/build_msvc.bat 2017
