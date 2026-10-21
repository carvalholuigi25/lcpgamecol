def __getattr__(name: str):
	if name != "router":
		raise AttributeError(name)
	from routes.games.routes import router
	return router


__all__ = ["router"]