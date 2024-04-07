import enum


class Roles(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

    def is_owner(self):
        return self == self.OWNER

    def is_admin(self):
        return self == self.ADMIN

    def is_member(self):
        return self == self.MEMBER
