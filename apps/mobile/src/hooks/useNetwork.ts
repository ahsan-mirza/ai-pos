import NetInfo from "@react-native-community/netinfo";
import { useEffect, useState } from "react";

export function useNetwork(): { online: boolean } {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setOnline(state.isConnected !== false);
    });
    return unsubscribe;
  }, []);
  return { online };
}
