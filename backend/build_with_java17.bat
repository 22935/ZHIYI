@echo off
set JAVA_HOME=D:\java 17
set PATH=D:\java 17\bin;%PATH%

java -version
mvn clean compile

if %ERRORLEVEL% EQU 0 (
    echo 构建成功！
    mvn spring-boot:run
) else (
    echo 构建失败，请检查错误信息
    pause
)