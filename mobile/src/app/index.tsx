import { createStaticNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import HomeScreen from './home';
import GamesScreen from './games';
import GamesDetailsScreen from './games/[gameId]';

const RootStack = createNativeStackNavigator({
  screens: {
    Home: {
      screen: HomeScreen,
      options: {
        title: 'Welcome',
      },
    },
    Games: {
      screen: GamesScreen,
      options: {
        title: 'Games',
      },
    },
    GamesDetails: {
      screen: GamesDetailsScreen,
      options: {
        title: 'Game Details',
      },
      params: {
        gameId: 'string',
      },
    },
  },
});

const Navigation = createStaticNavigation(RootStack);

export default function App() {
  return <Navigation />;
}
