from sqlalchemy.types import TypeDecorator, String

class EnumAsString(TypeDecorator):
    impl = String

    def __init__(self, enum_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enum_class = enum_class

    def process_bind_param(self, value, dialect):
        if isinstance(value, self.enum_class):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return self.enum_class(value)
        return value