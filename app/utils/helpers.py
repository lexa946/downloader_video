
def remove_all_spec_chars(key: str) -> str:
    new_key_list = []
    for char_ in key:
        if char_.isalnum():
            new_key_list.append(char_)
        elif char_.isspace():
            new_key_list.append("_")
    return "".join(new_key_list)