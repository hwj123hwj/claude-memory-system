from app import should_allow_new_file_creation, should_allow_write_tools


def test_allow_write_tools_when_user_explicitly_requests_save() -> None:
    assert should_allow_write_tools("请把这条记忆保存到inbox文件") is True


def test_disallow_write_tools_when_user_only_requests_a_plan() -> None:
    assert should_allow_write_tools("帮我出一个北京旅游计划") is False


def test_allow_new_file_creation_when_user_explicitly_requests_new_file() -> None:
    assert should_allow_new_file_creation("请单独新建文件保存这份计划") is True
