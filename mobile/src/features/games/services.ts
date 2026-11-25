export type Game = {
  id: string;
  name: string;
  description: string;
  image: string;
};

export async function fetchGames(): Promise<Game[]> {
  const response = await fetch('https://api.example.com/games');
  if (!response.ok) {
    throw new Error('Failed to fetch games');
  }
  const data = await response.json();
  return data as Game[];
}
