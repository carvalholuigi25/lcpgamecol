export type GameCollection = {
  id: string;
  name: string;
  description: string;
  image: string;
};

export async function fetchGamesCollections(): Promise<GameCollection[]> {
  const response = await fetch('https://api.example.com/game-collections');
  if (!response.ok) {
    throw new Error('Failed to fetch game collections');
  }

  const data = await response.json();
  return data as GameCollection[];
}
