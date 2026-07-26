
import pytest
from fastapi.testclient import TestClient

import server


client = TestClient(server.app)


def test_safe_path_rejects_sibling_prefix_traversal():
    with pytest.raises(Exception) as error:
        server.safe_path("../tmp-sibling/file.txt")
    assert "Path traversal" in str(error.value)


@pytest.mark.parametrize(
    "path",
    [
        "report.txt.",       # 尾随点：Win32 剥掉后覆盖 report.txt
        "report.txt ",       # 尾随空格：同理
        "sub/report.txt.",   # 非首段也要查
        "NUL",               # 保留设备名：写入"成功"但数据蒸发
        "nul.txt",           # 带扩展名也危险
        "COM1",              # 打开串口，可能挂死同步 open()
        "sub/PRN",
    ],
)
def test_safe_path_rejects_windows_aliases(path):
    """Windows 路径别名会让"写新文件"静默变成别的事，必须在 safe_path 就拦下。

    这些不是路径穿越（都在 workspace 内），resolve()+relative_to 放行它们，
    所以之前一路通到 open()：尾随点覆盖已有文件、设备名数据蒸发。
    """
    with pytest.raises(Exception) as error:
        server.safe_path(path)
    assert error.value.status_code == 400


@pytest.mark.parametrize("path", [".", "sub/../a.txt", "a.b.txt", "正常文件.md"])
def test_safe_path_allows_normal_and_dot_segments(path):
    """. 和界内的 .. 是合法路径段，不能被别名规则（尾随点）误伤成 400。"""
    server.safe_path(path)  # 不抛即通过


def test_safe_path_dotdot_segment_is_traversal_not_alias(path=".."):
    """单独的 .. 会越界，应是 403 路径穿越——而不是被别名规则当成 400。"""
    with pytest.raises(Exception) as error:
        server.safe_path(path)
    assert error.value.status_code == 403


def test_list_files_paths_are_workspace_relative(tmp_path, monkeypatch):
    """列目录返回的 path 必须相对 workspace，不能泄露宿主机绝对路径 / 用户名。

    起因：relpath 曾以未 resolve 的 WORKSPACE_DIR 为基准，遇到 8.3 短名 /
    符号链接会算出 ..\\..\\job steam\\... 这种越权样式路径并带出真实用户名。
    """
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "WORKSPACE_PATH", tmp_path.resolve())
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    resp = client.get("/v1/files", params={"path": "."})
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert not item["path"].startswith(".."), item["path"]
        assert ":" not in item["path"]  # 不含盘符
        assert item["path"] == "a.txt"


def test_health_is_public():
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_token_protects_workspace_routes(monkeypatch):
    monkeypatch.setattr(server, "SANDBOX_TOKEN", "test-token")
    unauthorized = client.get("/v1/files")
    assert unauthorized.status_code == 401
    authorized = client.get("/v1/files", headers={"X-Sandbox-Token": "test-token"})
    assert authorized.status_code == 200
    monkeypatch.setattr(server, "SANDBOX_TOKEN", "")


def test_write_and_read_file_are_workspace_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "WORKSPACE_PATH", tmp_path.resolve())
    write = client.post("/v1/files/write", json={"path": "hello.txt", "content": "你好"})
    assert write.status_code == 200
    read = client.get("/v1/files/read", params={"path": "hello.txt"})
    assert read.status_code == 200
    assert read.json()["content"] == "你好"


def test_execute_keeps_utf8_stdout():
    response = client.post("/v1/execute", json={"code": "print('中文输出')", "language": "python"})
    assert response.status_code == 200
    assert "中文输出" in response.json()["output"]


def test_upload_rejects_invalid_content_length(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "WORKSPACE_PATH", tmp_path.resolve())
    response = client.post(
        "/v1/files/upload",
        content=b"data",
        headers={"Content-Length": "not-a-number", "X-File-Path": "bad.txt"},
    )
    assert response.status_code == 400


def test_download_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "WORKSPACE_PATH", tmp_path.resolve())
    target = tmp_path / "large.bin"
    target.write_bytes(b"0123456789")
    monkeypatch.setattr(server, "MAX_FILE_BYTES", 4)
    response = client.get("/v1/files/download", params={"path": "large.bin"})
    assert response.status_code == 413


def test_executed_code_cannot_read_host_secret(monkeypatch):
    # 用户代码在子进程里执行，不应继承宿主机密钥；只暴露白名单里的环境变量。
    monkeypatch.setenv("SANDBOX_TOKEN", "super-secret-token")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leak-me")
    response = client.post(
        "/v1/execute",
        json={
            "code": "import os; print(os.environ.get('SANDBOX_TOKEN', 'ABSENT'), os.environ.get('AWS_SECRET_ACCESS_KEY', 'ABSENT'))",
            "language": "python",
        },
    )
    assert response.status_code == 200
    output = response.json()["output"]
    assert "super-secret-token" not in output
    assert "leak-me" not in output
    assert "ABSENT ABSENT" in output
