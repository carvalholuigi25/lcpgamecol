import { View, Text, StyleSheet } from 'react-native';

export default function UserLoginScreen() {
  return (
    <View style={styles.container}>
      <Text>User Login Screen</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
