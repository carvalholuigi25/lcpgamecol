import { View, Text, StyleSheet } from 'react-native';

export default function UserMainScreen() {
  return (
    <View style={styles.container}>
      <Text>User Main Screen</Text>
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
