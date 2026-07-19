from enum import Enum


class RenderLayer(str, Enum):
    STATIC = "static"
    STATE = "state"
    DYNAMIC = "dynamic"


class RenderState:
    def __init__(self):
        self._dirty_layers = set(RenderLayer)
        self._versions = {layer: 0 for layer in RenderLayer}
        self._reasons = {layer: "initial" for layer in RenderLayer}

    def invalidate(self, *layers, reason=""):
        for layer in layers:
            if not isinstance(layer, RenderLayer):
                layer = RenderLayer(layer)
            self._dirty_layers.add(layer)
            self._versions[layer] += 1
            if reason:
                self._reasons[layer] = reason

    def invalidate_all(self, reason=""):
        self.invalidate(*RenderLayer, reason=reason)

    def is_dirty(self, layer):
        if not isinstance(layer, RenderLayer):
            layer = RenderLayer(layer)
        return layer in self._dirty_layers

    def mark_clean(self, *layers):
        for layer in layers:
            if not isinstance(layer, RenderLayer):
                layer = RenderLayer(layer)
            self._dirty_layers.discard(layer)

    def snapshot(self):
        return {
            layer.value: {
                "dirty": layer in self._dirty_layers,
                "version": self._versions[layer],
                "reason": self._reasons[layer],
            }
            for layer in RenderLayer
        }
