class CanvasLayoutService:
    def __init__(self):
        self.next_x = 80
        self.next_y = 80
        self.step_x = 280
        self.step_y = 140
        self.max_width = 1200

    def next_position(self) -> tuple[int, int]:
        x = self.next_x
        y = self.next_y

        self.next_x += self.step_x
        if self.next_x > self.max_width:
            self.next_x = 80
            self.next_y += self.step_y

        return x, y